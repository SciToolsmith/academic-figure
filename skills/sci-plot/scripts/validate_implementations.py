#!/usr/bin/env python3
"""Validate SciPlot's native implementation index and pack metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = SKILL_ROOT / "implementations" / "implementation-index.json"
VOCABULARY_PATH = SKILL_ROOT / "references" / "schema-vocabularies.json"
VOCABULARY = json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))
ALLOWED_STATUS = set(VOCABULARY["enums"]["native_implementation_status"])
ALLOWED_TASK_PHASES = set(VOCABULARY["enums"]["task_phase"])


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected an object")
    return payload


def safe_skill_path(relative: str) -> Path:
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
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(index_path: Path) -> dict[str, Any]:
    index = load_json(index_path)
    entries = index.get("implementations")
    if not isinstance(entries, list) or not entries:
        raise ValueError("implementation index must contain a non-empty list")

    ids: set[str] = set()
    validated: list[dict[str, Any]] = []
    errors: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("index contains a non-object entry")
            continue
        required_index = {"id", "version", "status", "backend", "manifest"}
        missing_index = sorted(required_index - set(entry))
        if missing_index:
            errors.append(
                f"{entry.get('id', '<unknown>')}: index missing {missing_index}"
            )
            continue
        implementation_id = entry["id"]
        if implementation_id in ids:
            errors.append(f"{implementation_id}: duplicate index id")
        ids.add(implementation_id)
        if entry["status"] not in ALLOWED_STATUS:
            errors.append(f"{implementation_id}: invalid status {entry['status']}")

        try:
            manifest_path = safe_skill_path(entry["manifest"])
            manifest = load_json(manifest_path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"{implementation_id}: {exc}")
            continue
        required_manifest = {
            "schema_version",
            "id",
            "version",
            "status",
            "backend",
            "source",
            "semantic_signature",
            "input_contract",
            "guards",
            "cli_contract",
            "outputs",
            "verification",
        }
        missing_manifest = sorted(required_manifest - set(manifest))
        if missing_manifest:
            errors.append(
                f"{implementation_id}: manifest missing {missing_manifest}"
            )
            continue
        for key in ("id", "version", "status"):
            if manifest[key] != entry[key]:
                errors.append(
                    f"{implementation_id}: {key} differs between index and manifest"
                )
        source = manifest["source"]
        if source.get("category") != "sciplot-native":
            errors.append(
                f"{implementation_id}: runnable implementation must be sciplot-native"
            )
        if source.get("license") != "Apache-2.0":
            errors.append(f"{implementation_id}: unsupported implementation license")
        if not isinstance(manifest["guards"], list) or not manifest["guards"]:
            errors.append(f"{implementation_id}: guards must be non-empty")
        semantic_signature = manifest["semantic_signature"]
        if not isinstance(semantic_signature, dict):
            errors.append(
                f"{implementation_id}: semantic_signature must be an object"
            )
            supported_phases: list[str] = []
        else:
            supported_phases = semantic_signature.get("supported_task_phases", [])
            if (
                not isinstance(supported_phases, list)
                or not supported_phases
                or not all(isinstance(value, str) for value in supported_phases)
            ):
                errors.append(
                    f"{implementation_id}: supported_task_phases must be a "
                    "non-empty string list"
                )
                supported_phases = []
            else:
                invalid_phases = sorted(
                    set(supported_phases) - ALLOWED_TASK_PHASES
                )
                if invalid_phases:
                    errors.append(
                        f"{implementation_id}: unsupported task phases "
                        f"{invalid_phases}"
                    )
                if len(supported_phases) != len(set(supported_phases)):
                    errors.append(
                        f"{implementation_id}: supported_task_phases contains "
                        "duplicates"
                    )

        pack = manifest_path.parent
        entrypoint_name = manifest["backend"].get("entrypoint")
        if (
            not isinstance(entrypoint_name, str)
            or Path(entrypoint_name).name != entrypoint_name
        ):
            errors.append(f"{implementation_id}: unsafe entrypoint")
            continue
        entrypoint = pack / entrypoint_name
        if not entrypoint.is_file():
            errors.append(f"{implementation_id}: entrypoint does not exist")
            continue
        try:
            compile(
                entrypoint.read_text(encoding="utf-8"),
                str(entrypoint),
                "exec",
            )
        except SyntaxError as exc:
            errors.append(f"{implementation_id}: entrypoint does not compile: {exc}")

        verification = manifest["verification"]
        expected_hash = verification.get("source_sha256")
        actual_hash = sha256(entrypoint)
        if expected_hash != actual_hash:
            errors.append(
                f"{implementation_id}: source hash mismatch "
                f"(expected {expected_hash}, actual {actual_hash})"
            )
        source_hashes = verification.get("source_files_sha256")
        if not isinstance(source_hashes, dict) or not source_hashes:
            errors.append(f"{implementation_id}: source_files_sha256 is required")
            source_hashes = {}
        actual_source_hashes: dict[str, str] = {}
        for filename, expected in source_hashes.items():
            if (
                not isinstance(filename, str)
                or Path(filename).name != filename
                or not isinstance(expected, str)
            ):
                errors.append(f"{implementation_id}: invalid source hash entry")
                continue
            source_file = pack / filename
            if not source_file.is_file():
                errors.append(f"{implementation_id}: source file not found: {filename}")
                continue
            actual = sha256(source_file)
            actual_source_hashes[filename] = actual
            if actual != expected:
                errors.append(
                    f"{implementation_id}: source hash mismatch for {filename}"
                )
            if source_file.suffix == ".py":
                try:
                    compile(
                        source_file.read_text(encoding="utf-8"),
                        str(source_file),
                        "exec",
                    )
                except SyntaxError as exc:
                    errors.append(
                        f"{implementation_id}: {filename} does not compile: {exc}"
                    )
        for field in ("fixture", "fixture_manifest"):
            relative = verification.get(field)
            if (
                not isinstance(relative, str)
                or Path(relative).is_absolute()
                or ".." in Path(relative).parts
                or not (pack / relative).is_file()
            ):
                errors.append(f"{implementation_id}: invalid {field}")

        fixture = pack / verification.get("fixture", "")
        fixture_manifest = pack / verification.get("fixture_manifest", "")
        try:
            figure_contract = safe_skill_path(
                verification.get("figure_contract", "")
            )
        except (TypeError, ValueError) as exc:
            errors.append(
                f"{implementation_id}: invalid verification figure_contract: {exc}"
            )
            figure_contract = SKILL_ROOT / "__invalid_figure_contract__"
        if not figure_contract.is_file():
            errors.append(
                f"{implementation_id}: verification figure_contract not found"
            )
        smoke_relative = verification.get("local_smoke_report")
        if (
            not isinstance(smoke_relative, str)
            or Path(smoke_relative).is_absolute()
            or ".." in Path(smoke_relative).parts
            or not (pack / smoke_relative).is_file()
        ):
            errors.append(f"{implementation_id}: invalid local_smoke_report")
        else:
            try:
                smoke = load_json(pack / smoke_relative)
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                errors.append(f"{implementation_id}: invalid smoke report: {exc}")
            else:
                if smoke.get("implementation_id") != implementation_id:
                    errors.append(
                        f"{implementation_id}: smoke report id does not match"
                    )
                if smoke.get("source_sha256") != actual_hash:
                    errors.append(
                        f"{implementation_id}: smoke report source hash mismatch"
                    )
                if smoke.get("source_files_sha256") != actual_source_hashes:
                    errors.append(
                        f"{implementation_id}: smoke report source-file hashes mismatch"
                    )
                if fixture.is_file() and smoke.get("fixture_sha256") != sha256(
                    fixture
                ):
                    errors.append(
                        f"{implementation_id}: smoke report fixture hash mismatch"
                    )
                if (
                    fixture_manifest.is_file()
                    and smoke.get("fixture_manifest_sha256")
                    != sha256(fixture_manifest)
                ):
                    errors.append(
                        f"{implementation_id}: smoke report fixture manifest hash mismatch"
                    )
                if (
                    figure_contract.is_file()
                    and smoke.get("figure_contract_sha256")
                    != sha256(figure_contract)
                ):
                    errors.append(
                        f"{implementation_id}: smoke report Figure Contract "
                        "hash mismatch"
                    )
                visual = smoke.get("final_size_visual_review", {})
                if entry["status"] == "verified" and not (
                    visual.get("completed") is True
                    and visual.get("result") == "PASS"
                ):
                    errors.append(
                        f"{implementation_id}: verified status requires a passed "
                        "final-size visual review"
                    )

        validated.append(
            {
                "id": implementation_id,
                "version": manifest["version"],
                "status": manifest["status"],
                "entrypoint": str(entrypoint.relative_to(SKILL_ROOT)),
                "source_sha256": actual_hash,
                "supported_task_phases": supported_phases,
            }
        )

    if errors:
        raise ValueError("\n".join(errors))
    return {
        "status": "valid",
        "implementations": validated,
        "count": len(validated),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate SciPlot native implementation packs."
    )
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(args.index)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"implementation validation failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2 if args.pretty else None,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
