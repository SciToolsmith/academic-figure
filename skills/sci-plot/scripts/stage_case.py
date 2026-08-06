#!/usr/bin/env python3
"""Inspect or stage an immutable SciPlot case source for adaptation.

Bundled case code is never executed in place. Staging copies exactly one
backend entrypoint and its preview into a new, empty task directory and writes
an adaptation ledger that must be completed before execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASE_INDEX = SKILL_ROOT / "references" / "case-index.json"
DEFAULT_ASSET_INDEX = SKILL_ROOT / "references" / "case-assets.json"
VOCABULARY_PATH = SKILL_ROOT / "references" / "schema-vocabularies.json"
VOCABULARY = json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))
ALLOWED_REUSE_LEVELS = set(
    VOCABULARY["policy_sets"]["stageable_reuse_level"]
)
RUNNABLE_IMPLEMENTATION_STATUS = set(
    VOCABULARY["policy_sets"]["runnable_case_implementation_status"]
)
BLOCKED_AUDIT_STATUS = set(
    VOCABULARY["policy_sets"]["blocked_case_audit_status"]
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def resolve_inside_skill(relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe skill-relative path: {relative}")
    resolved = (SKILL_ROOT / path).resolve()
    try:
        resolved.relative_to(SKILL_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"path escapes skill root: {relative}") from exc
    return resolved


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_catalogs(
    case_index_path: Path, asset_index_path: Path
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    semantic_payload = load_json(case_index_path)
    asset_payload = load_json(asset_index_path)
    semantic_cases = semantic_payload.get("cases")
    asset_cases = asset_payload.get("cases")
    if not isinstance(semantic_cases, list) or not isinstance(asset_cases, list):
        raise ValueError("both catalogs must contain a cases array")

    semantic_by_id: dict[str, dict[str, Any]] = {}
    asset_by_id: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for item in semantic_cases:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            errors.append("semantic catalog contains an invalid case")
            continue
        if item["id"] in semantic_by_id:
            errors.append(f"{item['id']}: duplicate semantic case")
        semantic_by_id[item["id"]] = item

    required_asset_fields = {
        "id",
        "pack",
        "entrypoints",
        "required_inputs",
        "input_availability",
        "render_proof",
        "provenance",
        "license",
        "smoke_status",
    }
    for item in asset_cases:
        if not isinstance(item, dict):
            errors.append("asset catalog contains a non-object case")
            continue
        missing = sorted(required_asset_fields - set(item))
        if missing:
            errors.append(f"{item.get('id', '<unknown>')}: missing {', '.join(missing)}")
            continue
        case_id = item["id"]
        if not isinstance(case_id, str) or not case_id:
            errors.append("asset catalog contains an invalid id")
            continue
        if case_id in asset_by_id:
            errors.append(f"{case_id}: duplicate asset case")
        asset_by_id[case_id] = item

        entrypoints = item["entrypoints"]
        if not isinstance(entrypoints, dict) or not entrypoints:
            errors.append(f"{case_id}: entrypoints must be a non-empty object")
            continue
        pack = resolve_inside_skill(item["pack"])
        if not pack.is_dir():
            errors.append(f"{case_id}: pack not found: {item['pack']}")
            continue
        for backend, filename in entrypoints.items():
            if backend not in {"python", "r"}:
                errors.append(f"{case_id}: unsupported backend {backend}")
            if not isinstance(filename, str) or Path(filename).name != filename:
                errors.append(f"{case_id}: unsafe entrypoint {filename!r}")
                continue
            if not (pack / filename).is_file():
                errors.append(f"{case_id}: entrypoint not found: {pack / filename}")
        if not isinstance(item["required_inputs"], list) or not all(
            isinstance(value, str)
            and value
            and Path(value).name == value
            for value in item["required_inputs"]
        ):
            errors.append(f"{case_id}: required_inputs must contain safe basenames")
        render_proof = resolve_inside_skill(item["render_proof"])
        if not render_proof.is_file():
            errors.append(f"{case_id}: render proof not found: {item['render_proof']}")

    missing_assets = sorted(set(semantic_by_id) - set(asset_by_id))
    extra_assets = sorted(set(asset_by_id) - set(semantic_by_id))
    if missing_assets:
        errors.append(f"semantic cases without code assets: {', '.join(missing_assets)}")
    if extra_assets:
        errors.append(f"code assets without semantic cases: {', '.join(extra_assets)}")
    if errors:
        raise ValueError("\n".join(errors))
    return semantic_by_id, asset_by_id, asset_payload


def describe(
    case_id: str,
    semantic_by_id: dict[str, dict[str, Any]],
    asset_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if case_id not in semantic_by_id:
        raise KeyError(f"unknown case: {case_id}")
    semantic = semantic_by_id[case_id]
    asset = asset_by_id[case_id]
    return {
        "id": case_id,
        "title": semantic["title"],
        "decision_family": semantic["decision_family"],
        "audit_status": semantic["audit_status"],
        "implementation_status": semantic["implementation_status"],
        "repair_gate": semantic.get("repair_gate", []),
        "blocked_reason": semantic.get("blocked_reason"),
        "preview": asset["render_proof"],
        "pack": asset["pack"],
        "entrypoints": asset["entrypoints"],
        "required_inputs": asset["required_inputs"],
        "input_availability": asset["input_availability"],
        "provenance": asset["provenance"],
        "license": asset["license"],
        "smoke_status": asset["smoke_status"],
        "execution_policy": "stage-before-edit; never execute bundled source in place",
    }


def ensure_empty_directory(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            raise ValueError(f"workdir exists and is not a directory: {path}")
        if any(path.iterdir()):
            raise ValueError(f"workdir must be empty: {path}")
    else:
        path.mkdir(parents=True)


def stage(args: argparse.Namespace, semantic: dict[str, Any], asset: dict[str, Any]) -> dict[str, Any]:
    if args.reuse_level not in ALLOWED_REUSE_LEVELS:
        raise ValueError(f"unsupported reuse level: {args.reuse_level}")
    if args.backend not in asset["entrypoints"]:
        raise ValueError(
            f"{args.case_id}: backend {args.backend!r} is unavailable; "
            f"choose from {', '.join(sorted(asset['entrypoints']))}"
        )
    if args.reuse_level in {"exact", "structural"}:
        if semantic["audit_status"] == "conditional" and not args.repair_gate_satisfied:
            raise ValueError(
                f"{args.case_id}: repair gate must be satisfied before "
                f"{args.reuse_level} reuse"
            )
        if semantic["audit_status"] in BLOCKED_AUDIT_STATUS:
            raise ValueError(
                f"{args.case_id}: {semantic['audit_status']} cases cannot be "
                f"used for {args.reuse_level} reuse"
            )
        if (
            semantic["implementation_status"] not in RUNNABLE_IMPLEMENTATION_STATUS
            and not args.allow_unverified
        ):
            raise ValueError(
                f"{args.case_id}: implementation status is "
                f"{semantic['implementation_status']}; use style-only or explicitly "
                "allow an unverified staged inspection"
            )

    workdir = args.workdir.resolve()
    ensure_empty_directory(workdir)
    pack = resolve_inside_skill(asset["pack"])
    source = pack / asset["entrypoints"][args.backend]
    staged_source = workdir / source.name
    shutil.copy2(source, staged_source)

    preview_source = resolve_inside_skill(asset["render_proof"])
    staged_preview = workdir / preview_source.name
    shutil.copy2(preview_source, staged_preview)

    ledger = {
        "schema_version": "0.1.0",
        "case_id": args.case_id,
        "backend": args.backend,
        "reuse_level": args.reuse_level,
        "source": {
            "category": asset["provenance"],
            "license": asset["license"],
            "skill_path": str(source.relative_to(SKILL_ROOT)),
            "sha256": sha256(source),
            "immutable": True,
        },
        "staged_entrypoint": staged_source.name,
        "preview": staged_preview.name,
        "semantic_status": {
            "audit_status": semantic["audit_status"],
            "implementation_status": semantic["implementation_status"],
            "repair_gate": semantic.get("repair_gate", []),
            "repair_gate_satisfied": bool(args.repair_gate_satisfied),
        },
        "inputs": {
            "required_filenames": asset["required_inputs"],
            "bundled": False,
            "field_mapping": [],
            "units": {},
            "category_order": [],
            "replicate_unit": None,
            "uncertainty_definition": None,
        },
        "transform_guards": [],
        "exclusions": [],
        "changes_from_source": [],
        "execution_state": "mapping-required",
        "notes": [
            "Do not execute until input meanings and transform guards are recorded.",
            "Demo or user data must not be mistaken for the original case evidence.",
        ],
    }
    ledger_path = workdir / "case-adaptation.json"
    ledger_path.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "status": "staged",
        "workdir": str(workdir),
        "entrypoint": str(staged_source),
        "preview": str(staged_preview),
        "ledger": str(ledger_path),
        "next_action": "complete the field mapping and transform guards before execution",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect or stage SciPlot case source code without executing it."
    )
    parser.add_argument("case_id", nargs="?")
    parser.add_argument("--case-index", type=Path, default=DEFAULT_CASE_INDEX)
    parser.add_argument("--asset-index", type=Path, default=DEFAULT_ASSET_INDEX)
    parser.add_argument("--list", action="store_true", help="List available case packs.")
    parser.add_argument("--describe", metavar="CASE_ID", help="Describe one case pack.")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--backend", choices=("python", "r"))
    parser.add_argument("--workdir", type=Path)
    parser.add_argument(
        "--reuse-level",
        choices=tuple(sorted(ALLOWED_REUSE_LEVELS)),
        default="structural",
    )
    parser.add_argument(
        "--repair-gate-satisfied",
        action="store_true",
        help="Record that every semantic repair gate was independently satisfied.",
    )
    parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help="Stage code whose implementation has not been runtime-verified.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        semantic_by_id, asset_by_id, asset_payload = load_catalogs(
            args.case_index, args.asset_index
        )
        if args.validate_only:
            result: Any = {
                "status": "valid",
                "cases": len(asset_by_id),
                "policy": asset_payload.get("policy", {}),
            }
        elif args.list:
            result = [
                describe(case_id, semantic_by_id, asset_by_id)
                for case_id in sorted(asset_by_id)
            ]
        elif args.describe:
            result = describe(args.describe, semantic_by_id, asset_by_id)
        else:
            if not args.case_id or not args.backend or not args.workdir:
                raise ValueError(
                    "staging requires CASE_ID, --backend, and --workdir"
                )
            result = stage(
                args, semantic_by_id[args.case_id], asset_by_id[args.case_id]
            )
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"case staging failed: {exc}", file=sys.stderr)
        return 2

    if args.json or isinstance(result, (dict, list)):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
