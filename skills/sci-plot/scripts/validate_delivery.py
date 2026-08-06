#!/usr/bin/env python3
"""Reconcile a Figure Contract with a Render Manifest and delivered files."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable, Optional


SCHEMA = "sciplot.delivery-validation/v1"
FIGURE_FORMATS = {"svg", "pdf", "png", "tiff"}
STATUS_ORDER = {"PASS": 0, "WARN": 1, "FAIL": 2}


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _status(checks: Iterable[dict[str, Any]]) -> str:
    worst = max(
        (STATUS_ORDER.get(str(item.get("status")), 2) for item in checks),
        default=2,
    )
    return ("PASS", "WARN", "FAIL")[worst]


def _check(
    checks: list[dict[str, Any]],
    check_id: str,
    status: str,
    evidence: str,
    **details: Any,
) -> None:
    item: dict[str, Any] = {
        "id": check_id,
        "status": status,
        "evidence": evidence,
    }
    if details:
        item["details"] = details
    checks.append(item)


def _format_from_item(item: dict[str, Any], name: str) -> Optional[str]:
    declared = item.get("format")
    if isinstance(declared, str):
        value = declared.lower()
    else:
        value = Path(name).suffix.lower().removeprefix(".")
    return "tiff" if value in {"tif", "tiff"} else value or None


def _artifact_path(root: Path, name: str) -> Path:
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe artifact path: {name}")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"artifact path escapes artifact directory: {name}") from exc
    return candidate


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


def validate_delivery(
    contract_path: Path,
    manifest_path: Path,
    artifact_dir: Path,
) -> dict[str, Any]:
    contract = _load(contract_path)
    manifest = _load(manifest_path)
    checks: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []

    target = contract.get("target")
    if not isinstance(target, dict):
        _check(checks, "DV-01", "FAIL", "Figure Contract has no target object")
        target = {}
    declared_formats = target.get("formats")
    if (
        not isinstance(declared_formats, list)
        or not declared_formats
        or not all(isinstance(value, str) for value in declared_formats)
    ):
        _check(
            checks,
            "DV-01",
            "FAIL",
            "Figure Contract target.formats is not a non-empty string list",
        )
        declared_figure_formats: set[str] = set()
    else:
        declared_figure_formats = set(declared_formats)

    binding = manifest.get("figure_contract")
    recorded_contract_hash = (
        binding.get("sha256") if isinstance(binding, dict) else None
    )
    actual_contract_hash = _sha256(contract_path)
    if recorded_contract_hash != actual_contract_hash:
        _check(
            checks,
            "DV-01",
            "FAIL",
            "Render Manifest is not bound to the supplied Figure Contract hash",
            expected=actual_contract_hash,
            recorded=recorded_contract_hash,
        )
    else:
        _check(
            checks,
            "DV-01",
            "PASS",
            "Render Manifest Figure Contract hash matches",
        )

    manifest_artifacts = manifest.get("artifacts")
    if not isinstance(manifest_artifacts, list):
        _check(
            checks,
            "DV-04",
            "FAIL",
            "Render Manifest artifacts must be an array",
        )
        manifest_artifacts = []

    observed_figure_formats: set[str] = set()
    artifact_failures: list[str] = []
    for index, item in enumerate(manifest_artifacts, start=1):
        if not isinstance(item, dict):
            artifact_failures.append(f"artifact[{index}] is not an object")
            continue
        name = item.get("file", item.get("path"))
        if not isinstance(name, str) or not name:
            artifact_failures.append(f"artifact[{index}] has no file/path")
            continue
        output_format = _format_from_item(item, name)
        if output_format in FIGURE_FORMATS:
            observed_figure_formats.add(output_format)
        try:
            path = _artifact_path(artifact_dir, name)
        except ValueError as exc:
            artifact_failures.append(str(exc))
            continue
        if not path.is_file():
            artifact_failures.append(f"artifact does not exist: {name}")
            continue
        expected_hash = item.get("sha256")
        actual_hash = _sha256(path)
        if not isinstance(expected_hash, str) or expected_hash != actual_hash:
            artifact_failures.append(f"artifact hash mismatch: {name}")
        artifacts.append(
            {
                "path": str(path),
                "format": output_format,
                "sha256": actual_hash,
            }
        )

    if artifact_failures:
        _check(
            checks,
            "DV-04",
            "FAIL",
            "one or more manifest artifacts are missing, unsafe, or unverified",
            failures=artifact_failures,
        )
    else:
        _check(
            checks,
            "DV-04",
            "PASS",
            f"{len(artifacts)} manifest artifact path(s) and hash(es) verified",
        )

    if declared_figure_formats != observed_figure_formats:
        _check(
            checks,
            "DV-02",
            "FAIL",
            "formal figure formats differ between contract and delivered manifest",
            contract=sorted(declared_figure_formats),
            delivered=sorted(observed_figure_formats),
        )
    else:
        _check(
            checks,
            "DV-02",
            "PASS",
            "formal figure formats match the Figure Contract",
            formats=sorted(observed_figure_formats),
        )

    figure = manifest.get("figure")
    dimension_failures: list[str] = []
    if not isinstance(figure, dict):
        dimension_failures.append("Render Manifest has no figure object")
        figure = {}
    width = figure.get("width_mm")
    declared_width = target.get("width_mm")
    if not (
        isinstance(width, (int, float))
        and not isinstance(width, bool)
        and isinstance(declared_width, (int, float))
        and not isinstance(declared_width, bool)
        and math.isclose(
            float(width),
            float(declared_width),
            rel_tol=0,
            abs_tol=1e-9,
        )
    ):
        dimension_failures.append("width_mm differs from target.width_mm")
    height = figure.get("height_mm")
    declared_height = target.get("height_mm")
    declared_height_max = target.get("height_mm_max")
    if not isinstance(height, (int, float)) or isinstance(height, bool):
        dimension_failures.append("Render Manifest height_mm is missing")
    elif (
        isinstance(declared_height, (int, float))
        and not isinstance(declared_height, bool)
    ):
        if not math.isclose(
            float(height),
            float(declared_height),
            rel_tol=0,
            abs_tol=1e-9,
        ):
            dimension_failures.append("height_mm differs from target.height_mm")
    elif (
        isinstance(declared_height_max, (int, float))
        and not isinstance(declared_height_max, bool)
    ):
        if float(height) > float(declared_height_max) + 1e-9:
            dimension_failures.append("height_mm exceeds target.height_mm_max")
    else:
        dimension_failures.append("contract has no usable height constraint")

    if declared_figure_formats & {"png", "tiff"}:
        recorded_dpi = figure.get("dpi_for_raster")
        declared_dpi = target.get("resolution_dpi")
        if not (
            isinstance(recorded_dpi, (int, float))
            and not isinstance(recorded_dpi, bool)
            and isinstance(declared_dpi, (int, float))
            and not isinstance(declared_dpi, bool)
            and math.isclose(
                float(recorded_dpi),
                float(declared_dpi),
                rel_tol=0,
                abs_tol=1e-9,
            )
        ):
            dimension_failures.append(
                "dpi_for_raster differs from target.resolution_dpi"
            )

    if dimension_failures:
        _check(
            checks,
            "DV-03",
            "FAIL",
            "Render Manifest delivery geometry differs from the contract",
            failures=dimension_failures,
        )
    else:
        _check(
            checks,
            "DV-03",
            "PASS",
            "Render Manifest dimensions and raster DPI match the contract",
        )

    status = _status(checks)
    unresolved = [
        {
            "id": item["id"],
            "status": item["status"],
            "evidence": item["evidence"],
        }
        for item in checks
        if item["status"] != "PASS"
    ]
    return {
        "schema": SCHEMA,
        "status": status,
        "checks": checks,
        "artifacts": artifacts,
        "unresolved": unresolved,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare a Figure Contract with its Render Manifest and delivered files."
        )
    )
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.output and any(
        _same_file_target(args.output, source)
        for source in (args.contract, args.manifest)
    ):
        print(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "status": "FAIL",
                    "error": "--output must not overwrite an input",
                }
            )
        )
        return 2
    try:
        result = validate_delivery(
            args.contract,
            args.manifest,
            args.artifact_dir,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(
            json.dumps(
                {"schema": SCHEMA, "status": "FAIL", "error": str(exc)}
            )
        )
        return 2
    rendered = json.dumps(
        result,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
    )
    if args.output:
        try:
            args.output.write_text(rendered + "\n", encoding="utf-8")
        except OSError as exc:
            print(
                json.dumps(
                    {"schema": SCHEMA, "status": "FAIL", "error": str(exc)}
                )
            )
            return 2
    else:
        print(rendered)
    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
