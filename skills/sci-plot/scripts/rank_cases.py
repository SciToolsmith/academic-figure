#!/usr/bin/env python3
"""Rank audited scientific-figure cases by semantic compatibility.

This is a candidate retriever, not a decision-maker. Hard scientific
constraints are applied before keyword similarity, and an empty result is a
valid outcome.
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
ALLOWED_CATALOG_STATUS = {"admitted", "reviewed", "conditional", "inspiration", "quarantined"}
ALLOWED_IMPLEMENTATION_STATUS = {
    "verified",
    "language-specific",
    "static-reviewed",
    "failed",
    "unreviewed",
}


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower()
    return re.sub(r"\s+", " ", value).strip()


def word_tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9][a-z0-9-]*|[\u4e00-\u9fff]{2,}", normalize(value)))


def csv_values(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        result.extend(part.strip() for part in value.split(",") if part.strip())
    return result


def load_and_validate(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("index must be an object containing a cases array")

    required = {
        "id",
        "title",
        "tier",
        "catalog_status",
        "implementation_status",
        "decision_family",
        "data_structures",
        "evidence_goals",
        "domains",
        "keywords",
        "asset",
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
        if case["catalog_status"] not in ALLOWED_CATALOG_STATUS:
            errors.append(f"{case_id}: invalid catalog_status")
        if case["implementation_status"] not in ALLOWED_IMPLEMENTATION_STATUS:
            errors.append(f"{case_id}: invalid implementation_status")
        asset = SKILL_ROOT / case["asset"]
        if not asset.is_file():
            errors.append(f"{case_id}: asset not found: {case['asset']}")
        for key in ("data_structures", "evidence_goals", "domains", "keywords"):
            if not isinstance(case[key], list) or not case[key]:
                errors.append(f"{case_id}: {key} must be a non-empty array")

    if errors:
        raise ValueError("\n".join(errors))
    return payload


def phrase_score(query: str, case: dict[str, Any]) -> tuple[float, list[str]]:
    if not query:
        return 0.0, []
    normalized_query = normalize(query)
    query_tokens = word_tokens(query)
    score = 0.0
    reasons: list[str] = []

    fields: list[tuple[str, list[str], float]] = [
        ("keyword", case["keywords"], 3.0),
        ("evidence", case["evidence_goals"], 2.5),
        ("structure", case["data_structures"], 2.0),
        ("domain", case["domains"], 1.0),
        ("family", [case["decision_family"]], 1.5),
        ("title", [case["title"]], 1.5),
    ]
    for label, values, weight in fields:
        field_hit = False
        for value in values:
            normalized_value = normalize(value)
            value_tokens = word_tokens(value)
            if normalized_value and (
                normalized_value in normalized_query or normalized_query in normalized_value
            ):
                score += weight
                field_hit = True
            overlap = query_tokens & value_tokens
            if overlap:
                score += weight * min(1.0, len(overlap) / max(1, len(value_tokens)))
                field_hit = True
        if field_hit:
            reasons.append(label)
    return score, reasons


def rank(args: argparse.Namespace, payload: dict[str, Any]) -> list[dict[str, Any]]:
    requested_structures = {normalize(v) for v in csv_values(args.structure)}
    requested_families = {normalize(v) for v in csv_values(args.family)}
    requested_domains = {normalize(v) for v in csv_values(args.domain)}
    results: list[dict[str, Any]] = []

    for case in payload["cases"]:
        status = case["catalog_status"]
        implementation = case["implementation_status"]
        if status == "quarantined" or implementation == "failed":
            continue
        if status == "conditional" and not args.include_conditional:
            continue

        case_structures = {normalize(v) for v in case["data_structures"]}
        case_family = normalize(case["decision_family"])
        if requested_structures and not requested_structures.issubset(case_structures):
            continue
        if requested_families and case_family not in requested_families:
            continue

        score, reasons = phrase_score(args.query, case)
        hard_reasons: list[str] = []
        if requested_structures:
            score += 10.0 * len(requested_structures)
            hard_reasons.append("data-structure")
        if requested_families:
            score += 8.0
            hard_reasons.append("decision-family")

        case_domains = {normalize(v) for v in case["domains"]}
        domain_overlap = requested_domains & case_domains
        if domain_overlap:
            score += 2.0 * len(domain_overlap)
            reasons.append("domain")

        if args.query and not reasons and not hard_reasons:
            continue

        score += {"admitted": 2.0, "reviewed": 1.0, "conditional": -1.0}.get(status, 0.0)
        if case["tier"] == "core":
            score += 0.5

        if not args.query and not hard_reasons and not requested_domains:
            score = 0.0
        results.append(
            {
                "id": case["id"],
                "title": case["title"],
                "score": round(score, 2),
                "tier": case["tier"],
                "catalog_status": status,
                "implementation_status": implementation,
                "decision_family": case["decision_family"],
                "matched": sorted(set(hard_reasons + reasons)),
                "asset": case["asset"],
            }
        )

    results.sort(
        key=lambda item: (
            -item["score"],
            item["catalog_status"] != "admitted",
            item["tier"] != "core",
            item["id"],
        )
    )
    if args.query and results and results[0]["score"] <= 0:
        return []
    return results[: args.limit]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Retrieve candidate cases after semantic hard gates."
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
        help="Preferred domain; repeat or provide comma-separated values.",
    )
    parser.add_argument(
        "--include-conditional",
        action="store_true",
        help="Include cases whose repair or review gate is still open.",
    )
    parser.add_argument("--limit", type=int, default=3, choices=range(1, 11))
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the index and referenced assets without ranking.",
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

    results = rank(args, payload)
    if args.json:
        print(
            json.dumps(
                {
                    "matches": results,
                    "no_suitable_case": not results,
                    "recommended_action": (
                        "compare-candidates"
                        if results
                        else "continue-principle-first-build-new"
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif not results:
        print("no suitable case; continue with principle-first build-new design")
    else:
        for item in results:
            matched = ",".join(item["matched"]) or "catalog-order"
            print(
                f"{item['id']}\t{item['score']:.2f}\t{item['catalog_status']}"
                f"\t{item['decision_family']}\t{matched}\t{item['title']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
