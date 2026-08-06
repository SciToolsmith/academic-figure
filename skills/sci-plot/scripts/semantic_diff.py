#!/usr/bin/env python3
"""Compare two Figure Contracts and flag unapproved scientific changes."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA = "sciplot.semantic-diff/v1"
SEMANTIC_PREFIXES = (
    "question",
    "claims",
    "data_integrity",
    "traceability",
)
SEMANTIC_PANEL_FIELDS = {
    "question",
    "evidence_role",
    "supports_claims",
    "data_source",
    "analysis_unit",
    "replicate_unit",
    "fields",
    "quantity_and_units",
    "statistics",
    "unique_contribution",
}


def load_payload(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
    else:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ValueError("YAML input requires PyYAML; use JSON for the dependency-free path") from exc
        payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ValueError("contract root must be an object")
    return payload


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def flatten(value: Any, path: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        if not value:
            return {path: {}}
        result: dict[str, Any] = {}
        for key in sorted(value):
            child = f"{path}.{key}" if path else str(key)
            result.update(flatten(value[key], child))
        return result
    if isinstance(value, list):
        if not value:
            return {path: []}
        result = {}
        for index, item in enumerate(value):
            result.update(flatten(item, f"{path}[{index}]"))
        return result
    return {path: value}


def classify(path: str) -> str:
    if any(
        path == prefix or path.startswith(prefix + ".") or path.startswith(prefix + "[")
        for prefix in SEMANTIC_PREFIXES
    ):
        return "semantic"
    if path.startswith("panels["):
        remainder = path.split("].", 1)
        if len(remainder) == 2:
            field = remainder[1].split(".", 1)[0].split("[", 1)[0]
            if field in SEMANTIC_PANEL_FIELDS:
                return "semantic"
    if path.startswith(("visual_system", "target", "implementation")):
        return "implementation"
    return "administrative"


def compare(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    left = flatten(before)
    right = flatten(after)
    changes: list[dict[str, Any]] = []
    for path in sorted(set(left) | set(right)):
        old = left.get(path, {"__missing__": True})
        new = right.get(path, {"__missing__": True})
        if old != new:
            changes.append(
                {
                    "path": path,
                    "class": classify(path),
                    "before": old,
                    "after": new,
                }
            )
    return changes


def is_allowed(path: str, allowed: list[str]) -> bool:
    return any(path == prefix or path.startswith(prefix + ".") or path.startswith(prefix + "[") for prefix in allowed)


def _same_file_target(left: Path, right: Path) -> bool:
    try:
        if left.resolve(strict=False) == right.resolve(strict=False):
            return True
    except (OSError, RuntimeError):
        pass
    try:
        return left.samefile(right)
    except (OSError, ValueError):
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Flag scientific meaning changes between two Figure Contracts."
    )
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument(
        "--allow-prefix",
        action="append",
        default=[],
        help="Explicitly approved changed path; repeat as needed.",
    )
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--output", type=Path, help="Write JSON here instead of stdout.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.output:
        conflict = next(
            (
                source
                for source in (args.before, args.after)
                if _same_file_target(args.output, source)
            ),
            None,
        )
        if conflict is not None:
            print(
                json.dumps(
                    {
                        "schema": SCHEMA,
                        "status": "FAIL",
                        "error": (
                            "--output must not refer to a comparison input: "
                            f"{conflict}"
                        ),
                    },
                    ensure_ascii=False,
                )
            )
            return 2
    try:
        before = load_payload(args.before)
        after = load_payload(args.after)
        changes = compare(before, after)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(
            json.dumps(
                {"schema": SCHEMA, "status": "FAIL", "error": str(exc)},
                ensure_ascii=False,
            )
        )
        return 2

    unapproved = [
        item
        for item in changes
        if item["class"] == "semantic" and not is_allowed(item["path"], args.allow_prefix)
    ]
    approved_semantic = [
        item
        for item in changes
        if item["class"] == "semantic" and is_allowed(item["path"], args.allow_prefix)
    ]
    status = "FAIL" if unapproved else "WARN" if approved_semantic else "PASS"
    check = {
        "id": "RV-01",
        "status": status,
        "message": (
            f"{len(unapproved)} unapproved semantic change(s)"
            if unapproved
            else f"{len(approved_semantic)} approved semantic change(s)"
            if approved_semantic
            else "no semantic changes detected"
        ),
        "details": {
            "unapproved_paths": [item["path"] for item in unapproved],
            "approved_paths": [item["path"] for item in approved_semantic],
        },
    }
    result = {
        "schema": SCHEMA,
        "status": status,
        "checks": [check],
        "before": {"path": str(args.before), "sha256": file_sha256(args.before)},
        "after": {"path": str(args.after), "sha256": file_sha256(args.after)},
        "changes": changes,
        "unapproved_semantic_changes": unapproved,
        "approved_semantic_changes": approved_semantic,
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.output:
        try:
            args.output.write_text(rendered + "\n", encoding="utf-8")
        except OSError as exc:
            print(
                json.dumps(
                    {"schema": SCHEMA, "status": "FAIL", "error": str(exc)},
                    ensure_ascii=False,
                )
            )
            return 2
    else:
        print(rendered)
    return 1 if status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
