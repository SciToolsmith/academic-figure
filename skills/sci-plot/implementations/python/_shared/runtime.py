"""Shared guarded runtime for SciPlot-native Python renderers."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
import os
import sys
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Optional


ALLOWED_FORMATS = ("svg", "pdf", "png")
PROVENANCE_ONLY_COLUMNS = frozenset({"source_type"})


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def csv_semantic_fingerprint(
    path: Path,
    *,
    role_columns: Optional[dict[str, str]] = None,
    numeric_roles: Optional[Iterable[str]] = None,
) -> tuple[list[str], Optional[str]]:
    """Hash CSV scientific content while excluding provenance-only fields.

    The projection is insensitive to row order, physical column order, UTF-8
    BOMs, surrounding whitespace, equivalent decimal notation, and mapped
    column names. Unrelated extra columns are ignored so renaming or adding a
    provenance field cannot make a bundled demo appear to be production data.
    """

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        if len(fieldnames) != len(set(fieldnames)):
            raise ValueError(
                f"cannot fingerprint CSV with duplicate columns: {path}"
            )
        bindings = (
            {
                field: field
                for field in fieldnames
                if field.strip().lower() not in PROVENANCE_ONLY_COLUMNS
            }
            if role_columns is None
            else dict(role_columns)
        )
        roles = sorted(bindings)
        actual_columns = list(bindings.values())
        if (
            not roles
            or len(actual_columns) != len(set(actual_columns))
            or not set(actual_columns).issubset(fieldnames)
        ):
            return roles, None
        numeric = set(numeric_roles or [])
        rows = []
        for row in reader:
            canonical_row = []
            for role in roles:
                value = (row.get(bindings[role]) or "").strip()
                if role in numeric:
                    try:
                        decimal_value = Decimal(value)
                    except InvalidOperation:
                        pass
                    else:
                        if decimal_value.is_finite():
                            value = (
                                "0"
                                if decimal_value == 0
                                else format(decimal_value.normalize(), "f")
                            )
                canonical_row.append((role, value))
            rows.append(canonical_row)
    rows.sort()
    canonical = json.dumps(
        {"roles": roles, "rows": rows},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return roles, hashlib.sha256(canonical).hexdigest()


def split_list(value: Optional[str]) -> Optional[list[str]]:
    if value is None:
        return None
    items = [item.strip() for item in value.split(",")]
    if not items or any(not item for item in items):
        raise ValueError("comma-separated lists cannot contain empty values")
    if len(items) != len(set(items)):
        raise ValueError("comma-separated lists cannot contain duplicates")
    return items


def exact_order(
    label: str,
    declared: Optional[list[str]],
    observed: list[str],
    *,
    check_id: str,
) -> list[str]:
    if declared is None:
        return observed
    missing = sorted(set(observed) - set(declared))
    extra = sorted(set(declared) - set(observed))
    if missing or extra:
        raise ValueError(
            f"{check_id} {label} does not exactly cover observed values; "
            f"missing={missing}, extra={extra}"
        )
    return declared


def parse_formats(value: str) -> list[str]:
    formats = split_list(value)
    if formats is None:
        raise ValueError("at least one output format is required")
    unsupported = sorted(set(formats) - set(ALLOWED_FORMATS))
    if unsupported:
        raise ValueError(f"unsupported output formats: {unsupported}")
    return formats


def load_data_manifest(
    manifest_path: Path,
    input_paths: Iterable[Path],
    run_mode: str,
    *,
    check_id: str,
    bundled_demo_paths: Optional[Iterable[Path]] = None,
    semantic_column_bindings: Optional[dict[str, str]] = None,
    numeric_semantic_roles: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    resolved = manifest_path.resolve()
    if not resolved.is_file():
        raise ValueError(f"{check_id} data manifest not found: {resolved}")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{check_id} invalid data manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{check_id} data manifest must be an object")
    for field in ("synthetic", "production_use_allowed", "inputs"):
        if field not in payload:
            raise ValueError(f"{check_id} data manifest is missing {field}")
    if not isinstance(payload["synthetic"], bool) or not isinstance(
        payload["production_use_allowed"], bool
    ):
        raise ValueError(
            f"{check_id} synthetic and production_use_allowed must be booleans"
        )
    declared_inputs = payload["inputs"]
    if not isinstance(declared_inputs, dict) or not declared_inputs:
        raise ValueError(f"{check_id} inputs must be a non-empty object")
    resolved_inputs: list[Path] = []
    actual: dict[str, str] = {}
    for path in input_paths:
        resolved_input = path.resolve()
        if not resolved_input.is_file():
            raise ValueError(f"{check_id} input file not found: {resolved_input}")
        resolved_inputs.append(resolved_input)
        actual[resolved_input.name] = sha256(resolved_input)
    if declared_inputs != actual:
        raise ValueError(
            f"{check_id} manifest input hashes differ; "
            f"declared={declared_inputs}, actual={actual}"
        )
    if run_mode == "production":
        if payload["synthetic"] or not payload["production_use_allowed"]:
            raise ValueError(
                f"{check_id} production requires non-synthetic authorized inputs"
            )
        demo_paths = [
            path.resolve()
            for path in (bundled_demo_paths or [])
            if path.resolve().is_file()
        ]
        demo_hashes = {sha256(path) for path in demo_paths}
        byte_or_path_match = any(
            path in demo_paths or actual[path.name] in demo_hashes
            for path in resolved_inputs
        )
        semantic_match = False
        for demo_path in demo_paths:
            demo_bindings = (
                {
                    role: role
                    for role in semantic_column_bindings
                }
                if semantic_column_bindings is not None
                else None
            )
            demo_roles, demo_semantic_hash = csv_semantic_fingerprint(
                demo_path,
                role_columns=demo_bindings,
                numeric_roles=numeric_semantic_roles,
            )
            for input_path in resolved_inputs:
                _, input_semantic_hash = csv_semantic_fingerprint(
                    input_path,
                    role_columns=(
                        semantic_column_bindings
                        if semantic_column_bindings is not None
                        else {role: role for role in demo_roles}
                    ),
                    numeric_roles=numeric_semantic_roles,
                )
                if (
                    demo_semantic_hash is not None
                    and input_semantic_hash == demo_semantic_hash
                ):
                    semantic_match = True
                    break
            if semantic_match:
                break
        if byte_or_path_match or semantic_match:
            raise ValueError(
                f"{check_id} bundled demo inputs, including byte-identical or "
                "provenance-only modified copies, cannot be used in production"
            )
    elif not payload["synthetic"] or payload["production_use_allowed"]:
        raise ValueError(
            f"{check_id} smoke mode requires synthetic non-production inputs"
        )
    payload["_path"] = str(resolved)
    payload["_sha256"] = sha256(resolved)
    return payload


def bind_native_semantics(
    figure_contract: dict[str, Any],
    actual: dict[str, Any],
    *,
    check_id: str,
) -> None:
    """Bind renderer-controlled scientific semantics to the Figure Contract."""

    implementation = figure_contract.get("implementation")
    native = (
        implementation.get("native_implementation")
        if isinstance(implementation, dict)
        else None
    )
    declared = (
        native.get("semantic_bindings")
        if isinstance(native, dict)
        else None
    )
    if not isinstance(declared, dict):
        raise ValueError(
            f"{check_id} contract requires "
            "implementation.native_implementation.semantic_bindings"
        )
    missing = sorted(set(actual) - set(declared))
    extra = sorted(set(declared) - set(actual))
    mismatched = sorted(
        key
        for key in set(actual) & set(declared)
        if declared[key] != actual[key]
    )
    if missing or extra or mismatched:
        raise ValueError(
            f"{check_id} renderer semantics differ from the Figure Contract; "
            f"missing={missing}, extra={extra}, mismatched={mismatched}"
        )


def canonical_final_contract_report(
    payload: dict[str, Any],
    *,
    check_id: str,
) -> dict[str, Any]:
    """Apply the canonical final Figure Contract gate before production."""

    validator_path = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "validate_contract.py"
    )
    spec = importlib.util.spec_from_file_location(
        "sciplot_validate_contract",
        validator_path,
    )
    if spec is None or spec.loader is None:
        raise ValueError(
            f"{check_id} SCIPLOT-CONTRACT-FINAL validator is unavailable"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checker = getattr(module, "check_contract", None)
    summarizer = getattr(module, "summarize", None)
    if not callable(checker) or not callable(summarizer):
        raise ValueError(
            f"{check_id} SCIPLOT-CONTRACT-FINAL validator is invalid"
        )
    checks = checker(payload, stage="final")
    report = summarizer(checks, "final")
    if report.get("status") != "PASS":
        non_pass = [
            f"{item.get('id')}: {item.get('message')}"
            for item in checks
            if item.get("status") != "PASS"
        ]
        raise ValueError(
            f"{check_id} SCIPLOT-CONTRACT-FINAL requires PASS: "
            + "; ".join(non_pass)
        )
    return {
        "schema": report["schema"],
        "status": report["status"],
        "stage": report["stage"],
        "summary": report["summary"],
        "check_ids": [item["id"] for item in checks],
    }


def bind_figure_contract(
    contract_path: Path,
    *,
    implementation_id: str,
    implementation_version: str,
    supported_phases: set[str],
    run_mode: str,
    formats: list[str],
    width_mm: float,
    height_mm: float,
    dpi: int,
    included_rows: int,
    check_id: str,
) -> dict[str, Any]:
    resolved = contract_path.resolve()
    if not resolved.is_file():
        raise ValueError(f"{check_id} Figure Contract not found: {resolved}")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{check_id} invalid Figure Contract: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("contract_version") != 1:
        raise ValueError(f"{check_id} expected a version-1 Figure Contract")
    if run_mode == "production":
        payload["_contract_lint"] = canonical_final_contract_report(
            payload,
            check_id=check_id,
        )
    task = payload.get("task")
    target = payload.get("target")
    integrity = payload.get("data_integrity")
    if not isinstance(task, dict) or not isinstance(target, dict):
        raise ValueError(f"{check_id} contract requires task and target objects")
    if task.get("phase") not in supported_phases:
        raise ValueError(
            f"{check_id} unsupported task.phase {task.get('phase')!r}; "
            f"expected one of {sorted(supported_phases)}"
        )
    execution_state = task.get("execution_state")
    if execution_state == "blocked":
        raise ValueError(f"{check_id} blocked contracts cannot render")
    if run_mode == "production" and execution_state != "proceed":
        raise ValueError(f"{check_id} production requires execution_state=proceed")
    declared_formats = target.get("formats")
    if (
        not isinstance(declared_formats, list)
        or not declared_formats
        or not all(isinstance(item, str) for item in declared_formats)
        or set(declared_formats) != set(formats)
    ):
        raise ValueError(
            f"{check_id} CLI formats must exactly match target.formats"
        )
    declared_width = target.get("width_mm")
    if (
        not isinstance(declared_width, (int, float))
        or isinstance(declared_width, bool)
        or not math.isclose(
            float(declared_width), float(width_mm), rel_tol=0, abs_tol=1e-9
        )
    ):
        raise ValueError(f"{check_id} width_mm differs from the contract")
    declared_height = target.get("height_mm")
    declared_height_max = target.get("height_mm_max")
    if isinstance(declared_height, (int, float)) and not isinstance(
        declared_height, bool
    ):
        height_ok = math.isclose(
            float(declared_height), float(height_mm), rel_tol=0, abs_tol=1e-9
        )
    elif isinstance(declared_height_max, (int, float)) and not isinstance(
        declared_height_max, bool
    ):
        height_ok = height_mm <= float(declared_height_max) + 1e-9
    else:
        height_ok = False
    if not height_ok:
        raise ValueError(f"{check_id} height differs from the contract")
    if set(formats) & {"png", "tiff"}:
        declared_dpi = target.get("resolution_dpi")
        if (
            not isinstance(declared_dpi, (int, float))
            or isinstance(declared_dpi, bool)
            or not math.isclose(
                float(declared_dpi), float(dpi), rel_tol=0, abs_tol=1e-9
            )
        ):
            raise ValueError(f"{check_id} raster DPI differs from the contract")
    if not isinstance(integrity, dict) or integrity.get(
        "included_rows_or_items"
    ) != included_rows:
        raise ValueError(
            f"{check_id} included_rows_or_items must equal validated input rows"
        )
    implementation = payload.get("implementation")
    native = (
        implementation.get("native_implementation")
        if isinstance(implementation, dict)
        else None
    )
    if run_mode == "production" and not isinstance(native, dict):
        raise ValueError(
            f"{check_id} production requires implementation.native_implementation"
        )
    if isinstance(native, dict):
        if native.get("id") != implementation_id:
            raise ValueError(
                f"{check_id} native implementation id does not match"
            )
        if native.get("version") != implementation_version:
            raise ValueError(
                f"{check_id} native implementation version does not match"
            )
        if native.get("supported_task_phase") != task.get("phase"):
            raise ValueError(
                f"{check_id} native supported_task_phase does not match task.phase"
            )
    payload["_path"] = str(resolved)
    payload["_sha256"] = sha256(resolved)
    return payload


def bind_category_order(
    figure_contract: dict[str, Any],
    key: str,
    expected: list[str],
    *,
    check_id: str,
) -> None:
    """Require a renderer order to equal the Figure Contract order."""

    integrity = figure_contract.get("data_integrity")
    category_order = (
        integrity.get("category_order") if isinstance(integrity, dict) else None
    )
    declared = (
        category_order.get(key)
        if isinstance(category_order, dict)
        else None
    )
    if (
        not isinstance(declared, list)
        or not declared
        or not all(isinstance(item, str) and item for item in declared)
        or declared != expected
    ):
        raise ValueError(
            f"{check_id} CLI/data {key} order must exactly match "
            f"data_integrity.category_order.{key}; "
            f"contract={declared!r}, validated={expected!r}"
        )


def configure_matplotlib(implementation_id: str) -> tuple[Any, Any]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is required by this native implementation"
        ) from exc
    matplotlib.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "axes.unicode_minus": False,
            "svg.fonttype": "none",
            "svg.hashsalt": implementation_id,
            "pdf.fonttype": 42,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )
    return matplotlib, plt


def deterministic_offset(value: str, width: float = 0.18) -> float:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    fraction = int.from_bytes(digest[:4], "big") / (2**32 - 1)
    return (fraction * 2 - 1) * width


def quantile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("quantile requires at least one value")
    if not 0 <= probability <= 1:
        raise ValueError("probability must lie in [0, 1]")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def write_bundle(
    *,
    fig: Any,
    matplotlib: Any,
    output_dir: Path,
    basename: str,
    formats: list[str],
    dpi: int,
    width_mm: float,
    height_mm: float,
    title: str,
    implementation_id: str,
    implementation_version: str,
    source_files: dict[str, Path],
    input_paths: list[Path],
    data_manifest: dict[str, Any],
    figure_contract: Optional[dict[str, Any]],
    run_mode: str,
    rows_read: int,
    rows_included: int,
    field_mapping: dict[str, str],
    analysis_unit: str,
    replicate_unit: str,
    analysis_fieldnames: list[str],
    analysis_rows: list[dict[str, Any]],
    validation_checks: list[dict[str, Any]],
    data_details: dict[str, Any],
    figure_details: dict[str, Any],
    scientific_scope: dict[str, Any],
    warnings: Optional[list[str]] = None,
) -> dict[str, Any]:
    import matplotlib.pyplot as plt

    if output_dir.exists():
        if not output_dir.is_dir():
            raise ValueError(f"output path is not a directory: {output_dir}")
        if any(output_dir.iterdir()):
            raise ValueError(f"output directory must be empty: {output_dir}")
    else:
        output_dir.mkdir(parents=True)
    targets = [output_dir / f"{basename}.{fmt}" for fmt in formats]
    targets.extend(
        output_dir / name
        for name in (
            "analysis-table.csv",
            "data-validation.json",
            f"{basename}.manifest.json",
        )
    )
    if any(path.exists() for path in targets):
        raise ValueError("refusing to overwrite an existing output")

    artifacts: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix=f".{basename}-stage-", dir=output_dir
    ) as temporary:
        stage_dir = Path(temporary)
        for fmt in formats:
            staged = stage_dir / f"{basename}.{fmt}"
            metadata: dict[str, Any]
            if fmt == "svg":
                metadata = {
                    "Creator": f"SciPlot {implementation_id}",
                    "Date": None,
                }
            elif fmt == "pdf":
                metadata = {
                    "Creator": f"SciPlot {implementation_id}",
                    "Title": title,
                    "CreationDate": None,
                    "ModDate": None,
                }
            else:
                metadata = {"Software": f"SciPlot {implementation_id}"}
            fig.savefig(staged, format=fmt, dpi=dpi, metadata=metadata)
            artifacts.append(
                {
                    "file": staged.name,
                    "format": fmt,
                    "sha256": sha256(staged),
                    "bytes": staged.stat().st_size,
                }
            )
        plt.close(fig)

        analysis_path = stage_dir / "analysis-table.csv"
        with analysis_path.open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=analysis_fieldnames)
            writer.writeheader()
            writer.writerows(analysis_rows)
        artifacts.append(
            {
                "file": analysis_path.name,
                "format": "csv",
                "sha256": sha256(analysis_path),
                "bytes": analysis_path.stat().st_size,
            }
        )

        validation = {
            "schema_version": "sciplot.data-validation/v1",
            "status": (
                "PASS"
                if all(check.get("status") == "PASS" for check in validation_checks)
                else "FAIL"
            ),
            "implementation": implementation_id,
            "checks": validation_checks,
            "rows_read": rows_read,
            "rows_included": rows_included,
            "exclusions": [],
            "inputs": {
                path.name: sha256(path.resolve()) for path in input_paths
            },
            "data_manifest_sha256": data_manifest["_sha256"],
        }
        validation_path = stage_dir / "data-validation.json"
        validation_path.write_text(
            json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        artifacts.append(
            {
                "file": validation_path.name,
                "format": "json",
                "sha256": sha256(validation_path),
                "bytes": validation_path.stat().st_size,
            }
        )

        manifest = {
            "schema_version": "sciplot.render-manifest/v1",
            "figure_contract": (
                {
                    "file": figure_contract["_path"],
                    "sha256": figure_contract["_sha256"],
                    "phase": figure_contract["task"]["phase"],
                    "formats": figure_contract["target"]["formats"],
                    "lint": figure_contract.get("_contract_lint"),
                }
                if figure_contract
                else None
            ),
            "implementation": {
                "id": implementation_id,
                "version": implementation_version,
                "source_sha256": sha256(source_files["render.py"]),
                "source_files_sha256": {
                    name: sha256(path) for name, path in source_files.items()
                },
            },
            "data": {
                "run_mode": run_mode,
                "synthetic": data_manifest["synthetic"],
                "production_use_allowed": data_manifest[
                    "production_use_allowed"
                ],
                "input_files": {
                    path.name: str(path.resolve()) for path in input_paths
                },
                "input_sha256": {
                    path.name: sha256(path.resolve()) for path in input_paths
                },
                "data_manifest_file": data_manifest["_path"],
                "data_manifest_sha256": data_manifest["_sha256"],
                "rows_read": rows_read,
                "rows_included": rows_included,
                "exclusions": [],
                "field_mapping": field_mapping,
                "analysis_unit": analysis_unit,
                "replicate_unit": replicate_unit,
                **data_details,
            },
            "figure": {
                "width_mm": width_mm,
                "height_mm": height_mm,
                "dpi_for_raster": dpi,
                "tight_crop": False,
                **figure_details,
            },
            "scientific_scope": scientific_scope,
            "environment": {
                "python": sys.version.split()[0],
                "matplotlib": matplotlib.__version__,
            },
            "artifacts": artifacts,
            "warnings": warnings or [],
        }
        manifest_path = stage_dir / f"{basename}.manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        for staged in [
            *(stage_dir / item["file"] for item in artifacts),
            manifest_path,
        ]:
            os.replace(staged, output_dir / staged.name)
    return manifest
