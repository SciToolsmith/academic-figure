#!/usr/bin/env python3
"""Retrieve scientific-figure cases by semantic compatibility.

The catalog is an optional decision aid, not a template selector. Explicit
scientific constraints are hard gates. Query similarity is used only after
those gates, and an empty result is a valid, named outcome.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = SKILL_ROOT / "references" / "case-index.json"
DEFAULT_LEXICON = SKILL_ROOT / "references" / "retrieval-lexicon.json"
VOCABULARY_PATH = SKILL_ROOT / "references" / "schema-vocabularies.json"
VOCABULARY = json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))
ALLOWED_AUDIT_STATUS = set(VOCABULARY["enums"]["case_audit_status"])
ALLOWED_IMPLEMENTATION_STATUS = set(
    VOCABULARY["enums"]["case_implementation_status"]
)
BLOCKED_AUDIT_STATUS = set(
    VOCABULARY["policy_sets"]["blocked_case_audit_status"]
)
MIN_QUERY_RELEVANCE = 3.0


def normalize(value: str) -> str:
    """Normalize punctuation and spacing without translating meaning."""

    value = unicodedata.normalize("NFKC", value).lower()
    value = re.sub(r"[-_/]+", " ", value)
    value = re.sub(r"[^\w\u4e00-\u9fff]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def word_tokens(value: str) -> set[str]:
    """Tokenize Latin words and retain both CJK runs and their bigrams."""

    normalized = normalize(value)
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    for run in re.findall(r"[\u4e00-\u9fff]+", normalized):
        tokens.add(run)
        tokens.update(run[index : index + 2] for index in range(len(run) - 1))
    return tokens


def csv_values(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        result.extend(part.strip() for part in value.split(",") if part.strip())
    return result


def _is_string_list(value: Any, *, non_empty: bool = True) -> bool:
    return (
        isinstance(value, list)
        and (bool(value) or not non_empty)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def load_and_validate(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("index must be an object containing a cases array")

    lexicon_reference = payload.get("retrieval_lexicon")
    if not isinstance(lexicon_reference, str) or not lexicon_reference.strip():
        raise ValueError("retrieval_lexicon must be a non-empty skill-relative path")
    lexicon_relative = Path(lexicon_reference)
    if lexicon_relative.is_absolute() or ".." in lexicon_relative.parts:
        raise ValueError("retrieval_lexicon must not escape the skill root")
    lexicon_path = (SKILL_ROOT / lexicon_relative).resolve()
    try:
        lexicon_path.relative_to(SKILL_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("retrieval_lexicon must not escape the skill root") from exc
    with lexicon_path.open("r", encoding="utf-8") as handle:
        lexicon = json.load(handle)
    if (
        not isinstance(lexicon, dict)
        or lexicon.get("schema") != "sciplot.retrieval-lexicon/v1"
        or lexicon.get("lexicon_version") != 1
    ):
        raise ValueError("retrieval lexicon must use sciplot.retrieval-lexicon/v1")
    for axis in ("data_structure_aliases", "domain_aliases"):
        groups = lexicon.get(axis)
        if not isinstance(groups, dict) or not groups:
            raise ValueError(f"retrieval lexicon {axis} must be a non-empty object")
        for canonical, aliases in groups.items():
            if not isinstance(canonical, str) or not canonical.strip():
                raise ValueError(f"retrieval lexicon {axis} has an invalid key")
            if not _is_string_list(aliases):
                raise ValueError(
                    f"retrieval lexicon {axis}.{canonical} must be a "
                    "non-empty string array"
                )
    payload["_retrieval_lexicon"] = lexicon

    required = {
        "id",
        "title",
        "tier",
        "audit_status",
        "implementation_status",
        "decision_family",
        "data_structures",
        "evidence_goals",
        "domains",
        "keywords",
        "asset",
        "card",
    }
    seen: set[str] = set()
    errors: list[str] = []
    for position, case in enumerate(payload["cases"], start=1):
        missing = sorted(required - set(case)) if isinstance(case, dict) else sorted(required)
        if missing:
            errors.append(f"case {position}: missing {', '.join(missing)}")
            continue
        case_id = case["id"]
        if case_id in seen:
            errors.append(f"{case_id}: duplicate id")
        seen.add(case_id)
        if case["audit_status"] not in ALLOWED_AUDIT_STATUS:
            errors.append(f"{case_id}: invalid audit_status")
        if case["implementation_status"] not in ALLOWED_IMPLEMENTATION_STATUS:
            errors.append(f"{case_id}: invalid implementation_status")

        for key in ("asset", "card"):
            referenced_file = SKILL_ROOT / case[key]
            if not referenced_file.is_file():
                errors.append(f"{case_id}: {key} not found: {case[key]}")
        for key in ("data_structures", "evidence_goals", "domains", "keywords"):
            if not _is_string_list(case[key]):
                errors.append(f"{case_id}: {key} must be a non-empty string array")

        if case["audit_status"] == "conditional" and not _is_string_list(
            case.get("repair_gate")
        ):
            errors.append(f"{case_id}: conditional case requires a non-empty repair_gate")
        is_blocked = (
            case["audit_status"] in BLOCKED_AUDIT_STATUS
            or case["implementation_status"] == "failed"
        )
        if is_blocked and not isinstance(case.get("blocked_reason"), str):
            errors.append(f"{case_id}: blocked case requires blocked_reason")

    if errors:
        raise ValueError("\n".join(errors))
    return payload


def phrase_in_text(phrase: str, text: str) -> bool:
    """Return true for a complete normalized phrase, including Chinese phrases."""

    phrase = normalize(phrase)
    text = normalize(text)
    if not phrase or not text:
        return False
    if re.search(r"[\u4e00-\u9fff]", phrase):
        return phrase in text
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text))


def vocabulary_axis(payload: dict[str, Any], axis: str) -> dict[str, list[str]]:
    groups = payload["_retrieval_lexicon"][axis]
    return {
        normalize(canonical): [canonical, *aliases]
        for canonical, aliases in groups.items()
    }


def canonicalize_values(
    values: list[str], vocabulary: dict[str, list[str]]
) -> set[str]:
    alias_to_canonical = {
        normalize(alias): canonical
        for canonical, aliases in vocabulary.items()
        for alias in aliases
    }
    result: set[str] = set()
    for value in csv_values(values):
        normalized = normalize(value)
        result.add(alias_to_canonical.get(normalized, normalized))
    return result


def concepts_in_query(query: str, vocabulary: dict[str, list[str]]) -> dict[str, str]:
    """Map canonical concepts to the first non-negated controlled phrase."""

    hits: dict[str, str] = {}
    for canonical, aliases in vocabulary.items():
        for alias in sorted(aliases, key=lambda value: len(normalize(value)), reverse=True):
            if phrase_in_text(alias, query) and not phrase_is_negated(alias, query):
                hits[canonical] = alias
                break
    return hits


def phrase_is_negated(phrase: str, text: str) -> bool:
    """Detect a nearby, explicit negation without attempting full NLP."""

    phrase_normalized = normalize(phrase)
    text_normalized = normalize(text)
    if not phrase_normalized or not text_normalized:
        return False

    if re.search(r"[\u4e00-\u9fff]", phrase_normalized):
        start = text_normalized.find(phrase_normalized)
        if start < 0:
            return False
        prefix = text_normalized[max(0, start - 10) : start]
        return bool(
            re.search(
                r"(?:不是|并非|不属于|不采用|无需|没有|无|非|不)\s*$",
                prefix,
            )
        )

    match = re.search(
        rf"(?<![a-z0-9]){re.escape(phrase_normalized)}(?![a-z0-9])",
        text_normalized,
    )
    if not match:
        return False
    prefix_tokens = text_normalized[: match.start()].split()
    window = prefix_tokens[-3:]
    joined = " ".join(window)
    return bool(
        set(window) & {"not", "no", "without", "neither", "non"}
        or joined.endswith(("is not", "are not", "isn t", "aren t"))
    )


def negated_concepts_in_query(
    query: str, vocabulary: dict[str, list[str]]
) -> dict[str, str]:
    """Map canonical concepts to an explicitly negated controlled phrase."""

    hits: dict[str, str] = {}
    for canonical, aliases in vocabulary.items():
        for alias in sorted(aliases, key=lambda value: len(normalize(value)), reverse=True):
            if phrase_in_text(alias, query) and phrase_is_negated(alias, query):
                hits[canonical] = alias
                break
    return hits


def phrase_score(
    query: str, case: dict[str, Any]
) -> tuple[float, list[dict[str, str]]]:
    """Score lexical evidence conservatively, taking at most one hit per field."""

    if not query:
        return 0.0, []
    query_tokens = word_tokens(query)
    score = 0.0
    reasons: list[dict[str, str]] = []

    fields: list[tuple[str, list[str], float]] = [
        ("keyword", case["keywords"], 3.0),
        ("evidence_goal", case["evidence_goals"], 2.5),
        ("data_structure", case["data_structures"], 2.0),
        ("domain", case["domains"], 1.0),
        ("decision_family", [case["decision_family"]], 1.5),
        ("title", [case["title"]], 1.5),
    ]
    for axis, values, weight in fields:
        best_score = 0.0
        best_value = ""
        best_type = ""
        for value in values:
            if phrase_in_text(value, query) or phrase_in_text(query, value):
                candidate_score = weight
                match_type = "controlled-phrase"
            else:
                value_tokens = word_tokens(value)
                overlap = query_tokens & value_tokens
                candidate_score = (
                    weight * min(1.0, len(overlap) / max(1, len(value_tokens)))
                    if overlap
                    else 0.0
                )
                match_type = "token-overlap"
            if candidate_score > best_score:
                best_score = candidate_score
                best_value = value
                best_type = match_type
        if best_score:
            score += best_score
            reasons.append(
                {
                    "axis": axis,
                    "case_value": best_value,
                    "match_type": best_type,
                }
            )
    return score, reasons


def _case_result(
    case: dict[str, Any],
    *,
    score: float,
    relevance_score: float,
    reasons: list[dict[str, str]],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": case["id"],
        "title": case["title"],
        "score": round(score, 2),
        "relevance_score": round(relevance_score, 2),
        "tier": case["tier"],
        "audit_status": case["audit_status"],
        "implementation_status": case["implementation_status"],
        "reuse_readiness": (
            "repair-required"
            if case["audit_status"] == "conditional"
            else "ready"
        ),
        "decision_family": case["decision_family"],
        "match_reasons": reasons,
        "card": case["card"],
        "asset": case["asset"],
    }
    if case.get("repair_gate"):
        result["repair_gate"] = case["repair_gate"]
    if case.get("blocked_reason"):
        result["blocked_reason"] = case["blocked_reason"]
        result["reuse_readiness"] = "blocked"
    return result


def _sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -item["relevance_score"],
        item["audit_status"] != "admitted",
        item["tier"] != "core",
        item["id"],
    )


def retrieve(args: argparse.Namespace, payload: dict[str, Any]) -> dict[str, Any]:
    structure_vocabulary = vocabulary_axis(payload, "data_structure_aliases")
    domain_vocabulary = vocabulary_axis(payload, "domain_aliases")
    requested_structures = canonicalize_values(args.structure, structure_vocabulary)
    requested_families = {normalize(value) for value in csv_values(args.family)}
    requested_domains = canonicalize_values(args.domain, domain_vocabulary)
    # Explicit CLI constraints are authoritative. Query inference is a fallback,
    # not a second hard gate that can contradict the user's declared structure.
    query_structure_evidence = concepts_in_query(args.query, structure_vocabulary)
    query_structures = {} if requested_structures else query_structure_evidence
    negated_query_structures = (
        {}
        if requested_structures
        else negated_concepts_in_query(args.query, structure_vocabulary)
    )
    query_domains = concepts_in_query(args.query, domain_vocabulary)

    ready: list[dict[str, Any]] = []
    repair_required: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    constraint_only: list[dict[str, Any]] = []

    for case in payload["cases"]:
        case_structures = {normalize(value) for value in case["data_structures"]}
        case_family = normalize(case["decision_family"])
        case_domains = {normalize(value) for value in case["domains"]}

        # Explicit CLI constraints and controlled structure concepts in the query
        # are semantic gates, not preferences.
        if requested_structures and not requested_structures.issubset(case_structures):
            continue
        if requested_families and case_family not in requested_families:
            continue
        if requested_domains and not requested_domains.issubset(case_domains):
            continue
        if query_structures and not set(query_structures).issubset(case_structures):
            continue
        if set(negated_query_structures) & case_structures:
            continue

        relevance_score, reasons = phrase_score(args.query, case)
        if requested_structures:
            reasons.extend(
                {
                    "axis": "data_structure",
                    "case_value": value,
                    "match_type": "explicit-hard-gate",
                }
                for value in sorted(requested_structures)
            )
        if requested_families:
            reasons.append(
                {
                    "axis": "decision_family",
                    "case_value": case["decision_family"],
                    "match_type": "explicit-hard-gate",
                }
            )
        if requested_domains:
            reasons.extend(
                {
                    "axis": "domain",
                    "case_value": value,
                    "match_type": "explicit-hard-gate",
                }
                for value in sorted(requested_domains)
            )
        for canonical, alias in query_structure_evidence.items():
            if canonical in case_structures:
                relevance_score += 4.0
                reasons.append(
                    {
                        "axis": "data_structure",
                        "case_value": canonical,
                        "query_value": alias,
                        "match_type": "controlled-alias",
                    }
                )
        for canonical, alias in query_domains.items():
            if canonical in case_domains:
                relevance_score += 2.0
                reasons.append(
                    {
                        "axis": "domain",
                        "case_value": canonical,
                        "query_value": alias,
                        "match_type": "controlled-alias",
                    }
                )

        has_constraint = bool(
            requested_structures or requested_families or requested_domains
        )
        # Explicit constraints narrow the candidate set but never manufacture
        # semantic relevance. Keep below-threshold candidates visible as
        # diagnostics without allowing them to become matches.
        if args.query and relevance_score < MIN_QUERY_RELEVANCE:
            if has_constraint:
                result = _case_result(
                    case,
                    score=relevance_score,
                    relevance_score=relevance_score,
                    reasons=reasons,
                )
                result["match_basis"] = "constraint-only"
                result["semantic_threshold"] = MIN_QUERY_RELEVANCE
                result["constraint_only_reason"] = (
                    "semantic-relevance-below-threshold"
                )
                constraint_only.append(result)
            continue

        audit_status = case["audit_status"]
        implementation_status = case["implementation_status"]
        result = _case_result(
            case,
            score=relevance_score,
            relevance_score=relevance_score,
            reasons=reasons,
        )
        if args.query:
            result["match_basis"] = (
                "semantic-and-constraint" if has_constraint else "semantic"
            )
        elif has_constraint:
            result["match_basis"] = "constraint-only"
        else:
            result["match_basis"] = "catalog"

        if (
            audit_status in BLOCKED_AUDIT_STATUS
            or implementation_status == "failed"
        ):
            result["reuse_readiness"] = "blocked"
            blocked.append(result)
        elif audit_status == "conditional":
            repair_required.append(result)
        else:
            ready.append(result)

    ready.sort(key=_sort_key)
    repair_required.sort(key=_sort_key)
    blocked.sort(key=_sort_key)
    constraint_only.sort(key=_sort_key)

    ready = ready[: args.limit]
    repair_required = repair_required[: args.limit]
    blocked = blocked[: args.limit]
    constraint_only = constraint_only[: args.limit]
    matches = ready
    excluded_repair_candidates = repair_required
    if args.include_conditional:
        matches = sorted([*ready, *repair_required], key=_sort_key)[: args.limit]
        excluded_repair_candidates = []

    if matches:
        retrieval_status = "matched"
        recommended_action = (
            "compare-candidates-and-satisfy-any-repair-gates"
            if any(item["reuse_readiness"] == "repair-required" for item in matches)
            else "compare-candidates"
        )
    elif repair_required:
        retrieval_status = "repair-required-only"
        recommended_action = "satisfy-repair-gate-or-continue-principle-first-build-new"
    else:
        retrieval_status = "no-suitable-case"
        recommended_action = (
            "clarify-query-or-review-constraint-only-candidates-before-build-new"
            if constraint_only
            else "continue-principle-first-build-new"
        )

    return {
        "retrieval_status": retrieval_status,
        "matches": matches,
        "repair_required_candidates": excluded_repair_candidates,
        "blocked_candidates": blocked,
        "constraint_only_candidates": constraint_only,
        "no_suitable_case": retrieval_status == "no-suitable-case",
        "has_production_ready_match": any(
            item["reuse_readiness"] == "ready" for item in matches
        ),
        "recommended_action": recommended_action,
    }


def rank(args: argparse.Namespace, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Compatibility wrapper for callers that only consume eligible matches."""

    return retrieve(args, payload)["matches"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Retrieve optional case references after semantic hard gates."
    )
    parser.add_argument("--query", default="", help="Scientific question or evidence goal.")
    parser.add_argument(
        "--structure",
        action="append",
        default=[],
        help="Required data structure; repeat or provide comma-separated values.",
    )
    parser.add_argument(
        "--family",
        action="append",
        default=[],
        help="Required decision family; repeat or provide comma-separated values.",
    )
    parser.add_argument(
        "--domain",
        action="append",
        default=[],
        help="Required domain; repeat or provide comma-separated values.",
    )
    parser.add_argument(
        "--include-conditional",
        action="store_true",
        help="Include repair-required cases in matches; their gates remain mandatory.",
    )
    parser.add_argument("--limit", type=int, default=3, choices=range(1, 11))
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the index and referenced cards/assets without ranking.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        payload = load_and_validate(args.index)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"index validation failed:\n{exc}", file=sys.stderr)
        return 2

    if args.validate_only:
        print(f"valid: {len(payload['cases'])} cases")
        return 0

    outcome = retrieve(args, payload)
    if args.json:
        print(json.dumps(outcome, ensure_ascii=False, indent=2))
    elif outcome["retrieval_status"] == "no-suitable-case":
        if outcome["constraint_only_candidates"]:
            print(
                "no semantically suitable case; explicit constraints alone "
                "are insufficient"
            )
            print(
                "constraint-only candidates "
                "(semantic relevance is below threshold):"
            )
            for item in outcome["constraint_only_candidates"]:
                print(
                    f"{item['id']}\t{item['score']:.2f}\t{item['audit_status']}"
                    f"\t{item['decision_family']}\tcard={item['card']}"
                    f"\tasset={item['asset']}"
                )
        else:
            print("no suitable case; continue with principle-first build-new design")
        for item in outcome["blocked_candidates"]:
            print(
                f"blocked\t{item['id']}\t{item.get('blocked_reason', 'not reusable')}"
            )
    elif outcome["retrieval_status"] == "repair-required-only":
        print("repair-required candidates only; satisfy a gate or build new")
        for item in outcome["repair_required_candidates"]:
            gate = "; ".join(item["repair_gate"])
            print(
                f"{item['id']}\t{item['score']:.2f}\tconditional"
                f"\t{item['decision_family']}\tgate={gate}"
                f"\tcard={item['card']}\tasset={item['asset']}"
            )
    else:
        for item in outcome["matches"]:
            matched = ",".join(
                sorted({reason["axis"] for reason in item["match_reasons"]})
            ) or "catalog-order"
            gate = (
                f"\trepair_gate={'; '.join(item['repair_gate'])}"
                if item.get("repair_gate")
                else ""
            )
            print(
                f"{item['id']}\t{item['score']:.2f}\t{item['audit_status']}"
                f"\t{item['decision_family']}\t{matched}\t{item['title']}"
                f"\tcard={item['card']}\tasset={item['asset']}{gate}"
            )
        if outcome["repair_required_candidates"]:
            print("repair-required candidates (not production-ready matches):")
            for item in outcome["repair_required_candidates"]:
                gate = "; ".join(item["repair_gate"])
                print(
                    f"{item['id']}\t{item['score']:.2f}\tconditional"
                    f"\t{item['decision_family']}\tgate={gate}"
                    f"\tcard={item['card']}\tasset={item['asset']}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
