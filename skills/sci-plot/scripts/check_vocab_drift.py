#!/usr/bin/env python3
"""Fail when SciPlot's machine vocabularies drift from packaged data.

This checker deliberately covers stable machine enums only. Natural-language
retrieval aliases and transformation guard terms live in a separate lexicon
because they evolve by language and domain rather than by schema version.
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
DEFAULT_VOCABULARY = SKILL_ROOT / "references" / "schema-vocabularies.json"
DEFAULT_LEXICON = SKILL_ROOT / "references" / "retrieval-lexicon.json"
DEFAULT_CASE_INDEX = SKILL_ROOT / "references" / "case-index.json"
DEFAULT_IMPLEMENTATION_INDEX = (
    SKILL_ROOT / "implementations" / "implementation-index.json"
)

REQUIRED_ENUMS = {
    "contract_version",
    "validation_stage",
    "task_mode",
    "task_phase",
    "contract_profile",
    "execution_state",
    "claim_level",
    "claim_status",
    "evidence_role",
    "destination",
    "output_format",
    "reuse_level",
    "retrieval_status",
    "case_audit_status",
    "case_implementation_status",
    "risk_status",
    "native_implementation_status",
}


def load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def nested(payload: dict[str, Any], *path: str) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def normalize_alias(value: str) -> str:
    """Mirror retriever normalization so collisions cannot hide in punctuation."""

    value = unicodedata.normalize("NFKC", value).lower()
    value = re.sub(r"[-_/]+", " ", value)
    value = re.sub(r"[^\w\u4e00-\u9fff]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def validate(
    vocabulary_path: Path = DEFAULT_VOCABULARY,
    case_index_path: Path = DEFAULT_CASE_INDEX,
    implementation_index_path: Path = DEFAULT_IMPLEMENTATION_INDEX,
    lexicon_path: Path = DEFAULT_LEXICON,
) -> dict[str, Any]:
    vocabulary = load_object(vocabulary_path)
    if vocabulary.get("schema") != "sciplot.schema-vocabularies/v1":
        raise ValueError("unsupported schema-vocabularies schema")
    if vocabulary.get("vocabulary_version") != 1:
        raise ValueError("unsupported vocabulary_version")

    enums = vocabulary.get("enums")
    if not isinstance(enums, dict):
        raise ValueError("schema-vocabularies enums must be an object")
    missing = sorted(REQUIRED_ENUMS - set(enums))
    if missing:
        raise ValueError(f"schema-vocabularies is missing enums: {missing}")
    for name, values in enums.items():
        if not isinstance(values, list) or not values:
            raise ValueError(f"enum {name} must be a non-empty array")
        if len(values) != len({json.dumps(value, sort_keys=True) for value in values}):
            raise ValueError(f"enum {name} contains duplicate values")

    policy_sets = vocabulary.get("policy_sets")
    if not isinstance(policy_sets, dict):
        raise ValueError("schema-vocabularies policy_sets must be an object")
    subset_rules = {
        "blocked_case_audit_status": "case_audit_status",
        "stageable_reuse_level": "reuse_level",
        "runnable_case_implementation_status": "case_implementation_status",
    }
    for policy_name, enum_name in subset_rules.items():
        values = policy_sets.get(policy_name)
        if not isinstance(values, list) or not values:
            raise ValueError(f"policy set {policy_name} must be a non-empty array")
        unknown = sorted(set(values) - set(enums[enum_name]))
        if unknown:
            raise ValueError(
                f"policy set {policy_name} contains values outside {enum_name}: {unknown}"
            )

    lexicon = load_object(lexicon_path)
    if lexicon.get("schema") != "sciplot.retrieval-lexicon/v1":
        raise ValueError("unsupported retrieval-lexicon schema")
    if lexicon.get("lexicon_version") != 1:
        raise ValueError("unsupported lexicon_version")
    alias_group_count = 0
    lexicon_canonicals: dict[str, set[str]] = {}
    for axis in ("data_structure_aliases", "domain_aliases"):
        groups = lexicon.get(axis)
        if not isinstance(groups, dict) or not groups:
            raise ValueError(f"retrieval lexicon {axis} must be a non-empty object")
        aliases_seen: dict[str, str] = {}
        lexicon_canonicals[axis] = set()
        for canonical, aliases in groups.items():
            alias_group_count += 1
            if (
                not isinstance(canonical, str)
                or not canonical.strip()
                or not isinstance(aliases, list)
                or not aliases
                or not all(isinstance(alias, str) and alias.strip() for alias in aliases)
            ):
                raise ValueError(
                    f"retrieval lexicon {axis}.{canonical} must be a "
                    "non-empty string array"
                )
            lexicon_canonicals[axis].add(normalize_alias(canonical))
            for alias in [canonical, *aliases]:
                normalized = normalize_alias(alias)
                previous = aliases_seen.get(normalized)
                if previous is not None and previous != canonical:
                    raise ValueError(
                        f"retrieval lexicon {axis} alias {alias!r} maps to both "
                        f"{previous!r} and {canonical!r}"
                    )
                aliases_seen[normalized] = canonical
    for key in ("transformation_hints", "transformation_guard_tokens"):
        values = lexicon.get(key)
        if (
            not isinstance(values, list)
            or not values
            or not all(isinstance(value, str) and value.strip() for value in values)
            or len(values) != len(set(values))
        ):
            raise ValueError(f"retrieval lexicon {key} must contain unique strings")

    errors: list[str] = []
    case_index = load_object(case_index_path)
    if case_index.get("retrieval_lexicon") != "references/retrieval-lexicon.json":
        errors.append(
            "case index must reference references/retrieval-lexicon.json"
        )
    cases = case_index.get("cases")
    if not isinstance(cases, list):
        raise ValueError("case index must contain a cases array")
    case_axis_values = {
        "data_structure_aliases": {
            normalize_alias(value)
            for case in cases
            if isinstance(case, dict)
            for value in case.get("data_structures", [])
            if isinstance(value, str)
        },
        "domain_aliases": {
            normalize_alias(value)
            for case in cases
            if isinstance(case, dict)
            for value in case.get("domains", [])
            if isinstance(value, str)
        },
    }
    for axis, canonicals in lexicon_canonicals.items():
        orphaned = sorted(canonicals - case_axis_values[axis])
        if orphaned:
            errors.append(
                f"retrieval lexicon {axis} canonical values are not present "
                f"in the case index: {orphaned}"
            )
    for case in cases:
        if not isinstance(case, dict):
            errors.append("case index contains a non-object entry")
            continue
        case_id = case.get("id", "<unknown>")
        if case.get("audit_status") not in enums["case_audit_status"]:
            errors.append(f"{case_id}: audit_status is outside schema vocabulary")
        if (
            case.get("implementation_status")
            not in enums["case_implementation_status"]
        ):
            errors.append(
                f"{case_id}: implementation_status is outside schema vocabulary"
            )

    implementation_index = load_object(implementation_index_path)
    implementations = implementation_index.get("implementations")
    if not isinstance(implementations, list):
        raise ValueError("implementation index must contain an implementations array")
    for entry in implementations:
        if not isinstance(entry, dict):
            errors.append("implementation index contains a non-object entry")
            continue
        implementation_id = entry.get("id", "<unknown>")
        if entry.get("status") not in enums["native_implementation_status"]:
            errors.append(
                f"{implementation_id}: native implementation status is outside "
                "schema vocabulary"
            )

    contract_enum_paths = {
        ("task", "mode"): "task_mode",
        ("task", "phase"): "task_phase",
        ("task", "profile"): "contract_profile",
        ("task", "execution_state"): "execution_state",
        ("target", "destination"): "destination",
        ("target", "primary_format"): "output_format",
        ("target", "preview_format"): "output_format",
        ("implementation", "case_influence", "reuse_level"): "reuse_level",
        (
            "implementation",
            "case_influence",
            "retrieval_status",
        ): "retrieval_status",
        (
            "implementation",
            "case_influence",
            "audit_status_at_selection",
        ): "case_audit_status",
        (
            "implementation",
            "case_influence",
            "implementation_status_at_selection",
        ): "case_implementation_status",
    }
    examples = sorted(
        (SKILL_ROOT / "references").glob("figure-contract*.example.json")
    )
    for example_path in examples:
        contract = load_object(example_path)
        if contract.get("contract_version") not in enums["contract_version"]:
            errors.append(
                f"{example_path.name}: contract_version is outside schema vocabulary"
            )
        for path, enum_name in contract_enum_paths.items():
            value = nested(contract, *path)
            if value is not None and value not in enums[enum_name]:
                errors.append(
                    f"{example_path.name}: {'.'.join(path)}={value!r} is outside "
                    f"{enum_name}"
                )
        for index, claim in enumerate(contract.get("claims", [])):
            if not isinstance(claim, dict):
                continue
            for field, enum_name in (
                ("level", "claim_level"),
                ("status", "claim_status"),
            ):
                value = claim.get(field)
                if value is not None and value not in enums[enum_name]:
                    errors.append(
                        f"{example_path.name}: claims[{index}].{field}={value!r} "
                        f"is outside {enum_name}"
                    )
        for index, panel in enumerate(contract.get("panels", [])):
            if not isinstance(panel, dict):
                continue
            value = panel.get("evidence_role")
            if value is not None and value not in enums["evidence_role"]:
                errors.append(
                    f"{example_path.name}: panels[{index}].evidence_role={value!r} "
                    "is outside evidence_role"
                )
        formats = nested(contract, "target", "formats")
        if isinstance(formats, list):
            unknown_formats = sorted(set(formats) - set(enums["output_format"]))
            if unknown_formats:
                errors.append(
                    f"{example_path.name}: target.formats has unknown values "
                    f"{unknown_formats}"
                )
        for index, risk in enumerate(contract.get("review_risks", [])):
            if not isinstance(risk, dict):
                continue
            value = risk.get("status")
            if value is not None and value not in enums["risk_status"]:
                errors.append(
                    f"{example_path.name}: review_risks[{index}].status={value!r} "
                    "is outside risk_status"
                )

    if errors:
        raise ValueError("\n".join(errors))
    return {
        "schema": "sciplot.vocabulary-drift-report/v1",
        "status": "PASS",
        "vocabulary_version": vocabulary["vocabulary_version"],
        "lexicon_version": lexicon["lexicon_version"],
        "enum_count": len(enums),
        "alias_group_count": alias_group_count,
        "case_count": len(cases),
        "implementation_count": len(implementations),
        "contract_examples_checked": [path.name for path in examples],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate SciPlot machine vocabularies against packaged data."
    )
    parser.add_argument("--vocabulary", type=Path, default=DEFAULT_VOCABULARY)
    parser.add_argument("--lexicon", type=Path, default=DEFAULT_LEXICON)
    parser.add_argument("--case-index", type=Path, default=DEFAULT_CASE_INDEX)
    parser.add_argument(
        "--implementation-index",
        type=Path,
        default=DEFAULT_IMPLEMENTATION_INDEX,
    )
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    try:
        report = validate(
            args.vocabulary,
            args.case_index,
            args.implementation_index,
            args.lexicon,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"vocabulary drift check failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2 if args.pretty else None,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
