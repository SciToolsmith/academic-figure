"""Input, provenance, and transformation guards for composition-bars-v1."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any


DEFAULT_COLORS = (
    "#0072B2",
    "#E69F00",
    "#009E73",
    "#CC79A7",
    "#56B4E9",
    "#D55E00",
    "#F0E442",
    "#6B7280",
    "#332288",
    "#88CCEE",
    "#44AA99",
    "#AA4499",
)
ALLOWED_FORMATS = ("svg", "pdf", "png")
SUPPORTED_TASK_PHASES = ("descriptive", "presentation")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def split_list(value: str | None) -> list[str] | None:
    if value is None:
        return None
    items = [item.strip() for item in value.split(",")]
    if not items or any(not item for item in items):
        raise ValueError("comma-separated lists cannot contain empty values")
    if len(items) != len(set(items)):
        raise ValueError("comma-separated lists cannot contain duplicates")
    return items


def validate_order(
    name: str, declared: list[str] | None, observed: list[str]
) -> list[str]:
    if declared is None:
        return observed
    missing = sorted(set(observed) - set(declared))
    extra = sorted(set(declared) - set(observed))
    if missing or extra:
        raise ValueError(
            f"CB-ORDER-01 {name} does not exactly cover observed values; "
            f"missing={missing}, extra={extra}"
        )
    return declared


def parse_formats(value: str) -> list[str]:
    formats = split_list(value)
    if formats is None:
        raise ValueError("at least one output format is required")
    unsupported = sorted(set(formats) - set(ALLOWED_FORMATS))
    if unsupported:
        raise ValueError(f"unsupported output formats: {', '.join(unsupported)}")
    return formats


def load_data_manifest(
    manifest_path: Path, input_path: Path, run_mode: str
) -> dict[str, Any]:
    resolved = manifest_path.resolve()
    if not resolved.is_file():
        raise ValueError(f"CB-DEMO-01 data manifest not found: {resolved}")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"CB-DEMO-01 invalid data manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("CB-DEMO-01 data manifest must be an object")
    for field in ("synthetic", "production_use_allowed", "input_sha256"):
        if field not in payload:
            raise ValueError(f"CB-DEMO-01 data manifest is missing {field}")
    if not isinstance(payload["synthetic"], bool) or not isinstance(
        payload["production_use_allowed"], bool
    ):
        raise ValueError(
            "CB-DEMO-01 synthetic and production_use_allowed must be booleans"
        )
    actual_hash = sha256(input_path)
    if payload["input_sha256"] != actual_hash:
        raise ValueError(
            "CB-DEMO-01 data manifest input hash does not match the CSV"
        )
    if run_mode == "production":
        if payload["synthetic"] or not payload["production_use_allowed"]:
            raise ValueError(
                "CB-DEMO-01 production mode requires non-synthetic data with "
                "production_use_allowed=true"
            )
    elif not payload["synthetic"] or payload["production_use_allowed"]:
        raise ValueError(
            "CB-DEMO-01 smoke mode requires synthetic data with "
            "production_use_allowed=false"
        )
    payload["_path"] = str(resolved)
    payload["_sha256"] = sha256(resolved)
    return payload


def load_figure_contract(
    contract_path: Path,
    *,
    run_mode: str,
    value_mode: str,
    formats: list[str],
    width_mm: float,
    height_mm: float,
    dpi: int,
    rows: int,
    implementation_id: str,
) -> dict[str, Any]:
    """Bind a production render to its scientific and delivery contract."""

    resolved = contract_path.resolve()
    if not resolved.is_file():
        raise ValueError(
            f"CB-CONTRACT-01 Figure Contract not found: {resolved}"
        )
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"CB-CONTRACT-01 invalid JSON Figure Contract: {exc}"
        ) from exc
    if not isinstance(payload, dict) or payload.get("contract_version") != 1:
        raise ValueError(
            "CB-CONTRACT-01 Figure Contract must be a version-1 object"
        )

    task = payload.get("task")
    target = payload.get("target")
    data_integrity = payload.get("data_integrity")
    if not isinstance(task, dict) or not isinstance(target, dict):
        raise ValueError(
            "CB-CONTRACT-01 Figure Contract requires task and target objects"
        )
    phase = task.get("phase")
    if phase not in SUPPORTED_TASK_PHASES:
        raise ValueError(
            "CB-CONTRACT-01 composition-bars-v1 supports task.phase "
            f"{list(SUPPORTED_TASK_PHASES)}, not {phase!r}"
        )
    execution_state = task.get("execution_state")
    if run_mode == "production" and execution_state != "proceed":
        raise ValueError(
            "CB-CONTRACT-01 production requires execution_state=proceed"
        )
    if execution_state == "blocked":
        raise ValueError(
            "CB-CONTRACT-01 a blocked Figure Contract cannot be rendered"
        )
    if value_mode == "counts" and phase != "descriptive":
        raise ValueError(
            "CB-CONTRACT-01 count-to-share conversion requires "
            "task.phase=descriptive"
        )

    declared_formats = target.get("formats")
    if (
        not isinstance(declared_formats, list)
        or not declared_formats
        or not all(isinstance(value, str) for value in declared_formats)
        or len(declared_formats) != len(set(declared_formats))
    ):
        raise ValueError(
            "CB-CONTRACT-01 target.formats must be a non-empty unique string list"
        )
    if set(declared_formats) != set(formats):
        raise ValueError(
            "CB-CONTRACT-01 CLI formats do not match target.formats; "
            f"contract={declared_formats}, cli={formats}"
        )

    declared_width = target.get("width_mm")
    if (
        not isinstance(declared_width, (int, float))
        or isinstance(declared_width, bool)
        or declared_width <= 0
        or not math.isclose(
            float(declared_width),
            float(width_mm),
            rel_tol=0,
            abs_tol=1e-9,
        )
    ):
        raise ValueError(
            "CB-CONTRACT-01 CLI width_mm must equal target.width_mm"
        )
    declared_height = target.get("height_mm")
    declared_height_max = target.get("height_mm_max")
    if (
        isinstance(declared_height, (int, float))
        and not isinstance(declared_height, bool)
        and declared_height > 0
    ):
        if not math.isclose(
            float(declared_height),
            float(height_mm),
            rel_tol=0,
            abs_tol=1e-9,
        ):
            raise ValueError(
                "CB-CONTRACT-01 CLI height_mm must equal target.height_mm"
            )
    elif (
        isinstance(declared_height_max, (int, float))
        and not isinstance(declared_height_max, bool)
        and declared_height_max > 0
    ):
        if height_mm > float(declared_height_max) + 1e-9:
            raise ValueError(
                "CB-CONTRACT-01 CLI height_mm exceeds target.height_mm_max"
            )
    else:
        raise ValueError(
            "CB-CONTRACT-01 target requires a positive height_mm or height_mm_max"
        )

    if any(value in {"png", "tiff"} for value in formats):
        declared_dpi = target.get("resolution_dpi")
        if (
            not isinstance(declared_dpi, (int, float))
            or isinstance(declared_dpi, bool)
            or declared_dpi <= 0
            or not math.isclose(
                float(declared_dpi),
                float(dpi),
                rel_tol=0,
                abs_tol=1e-9,
            )
        ):
            raise ValueError(
                "CB-CONTRACT-01 CLI dpi must equal target.resolution_dpi "
                "when a raster output is declared"
            )

    if not isinstance(data_integrity, dict):
        raise ValueError(
            "CB-CONTRACT-01 Figure Contract requires data_integrity"
        )
    included = data_integrity.get("included_rows_or_items")
    if (
        not isinstance(included, int)
        or isinstance(included, bool)
        or included != rows
    ):
        raise ValueError(
            "CB-CONTRACT-01 included_rows_or_items must equal validated CSV rows"
        )
    if value_mode == "counts" and not data_integrity.get("transformations"):
        raise ValueError(
            "CB-CONTRACT-01 count mode requires an explicit transformation record"
        )

    implementation = payload.get("implementation")
    native = (
        implementation.get("native_implementation")
        if isinstance(implementation, dict)
        else None
    )
    if isinstance(native, dict) and native.get("id") not in {
        None,
        implementation_id,
    }:
        raise ValueError(
            "CB-CONTRACT-01 native implementation id does not match renderer"
        )

    payload["_path"] = str(resolved)
    payload["_sha256"] = sha256(resolved)
    return payload


def read_and_validate(
    args: argparse.Namespace, data_manifest: dict[str, Any]
) -> dict[str, Any]:
    path = args.input.resolve()
    if not path.is_file():
        raise ValueError(f"CB-INPUT-01 input file not found: {path}")
    if not 0 < args.sum_tolerance <= 0.001:
        raise ValueError("CB-DENOM-01 --sum-tolerance must be in (0, 0.001]")

    roles = {
        "sample": args.sample_col,
        "facet": args.facet_col,
        "category": args.category_col,
        "value": args.value_col,
    }
    if len(set(roles.values())) != len(roles):
        raise ValueError("CB-INPUT-01 role columns must be distinct")

    observed_facets: list[str] = []
    observed_categories: list[str] = []
    samples_by_facet: dict[str, list[str]] = {}
    values: dict[tuple[str, str, str], float] = {}
    records: list[tuple[str, str, str]] = []
    rows = 0

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        if not fieldnames:
            raise ValueError("CB-INPUT-01 input has no header")
        if len(fieldnames) != len(set(fieldnames)):
            raise ValueError("CB-INPUT-01 input contains duplicate column names")
        missing_columns = sorted(set(roles.values()) - set(fieldnames))
        if missing_columns:
            raise ValueError(
                "CB-INPUT-01 missing required columns: " + ", ".join(missing_columns)
            )
        if args.run_mode == "smoke" and "source_type" not in fieldnames:
            raise ValueError(
                "CB-DEMO-01 smoke input requires source_type=simulated on every row"
            )

        for line_number, row in enumerate(reader, start=2):
            rows += 1
            if args.run_mode == "smoke":
                if row.get("source_type", "").strip().lower() != "simulated":
                    raise ValueError(
                        f"CB-DEMO-01 line {line_number} is not marked simulated"
                    )
            elif row.get("source_type", "").strip().lower() == "simulated":
                raise ValueError(
                    "CB-DEMO-01 simulated rows require --run-mode smoke"
                )

            raw_sample = row[args.sample_col]
            raw_facet = row[args.facet_col]
            raw_category = row[args.category_col]
            if any(
                value != value.strip()
                for value in (raw_sample, raw_facet, raw_category)
            ):
                raise ValueError(
                    f"CB-INPUT-01 line {line_number} contains leading or "
                    "trailing whitespace in a role value"
                )
            sample = raw_sample
            facet = raw_facet
            category = raw_category
            if not sample or not facet or not category:
                raise ValueError(
                    f"CB-INPUT-01 line {line_number} has an empty role value"
                )
            try:
                value = float(row[args.value_col])
            except ValueError as exc:
                raise ValueError(
                    f"CB-VALUE-01 line {line_number} has a nonnumeric value"
                ) from exc
            if not math.isfinite(value) or value < 0:
                raise ValueError(
                    f"CB-VALUE-01 line {line_number} must be finite and nonnegative"
                )
            if args.value_mode == "proportion" and value > 1:
                raise ValueError(
                    f"CB-VALUE-01 line {line_number} proportion exceeds one"
                )

            key = (facet, sample, category)
            if key in values:
                raise ValueError(
                    "CB-KEY-01 duplicate facet-sample-category key: "
                    + " | ".join(key)
                )
            values[key] = value
            records.append(key)
            if facet not in observed_facets:
                observed_facets.append(facet)
                samples_by_facet[facet] = []
            if sample not in samples_by_facet[facet]:
                samples_by_facet[facet].append(sample)
            if category not in observed_categories:
                observed_categories.append(category)

    if rows == 0:
        raise ValueError("CB-INPUT-01 input contains no data rows")

    facets = validate_order(
        "facet order", split_list(args.facet_order), observed_facets
    )
    categories = validate_order(
        "category order", split_list(args.category_order), observed_categories
    )
    if len(facets) > 8:
        raise ValueError("implementation supports at most eight facets")
    if len(categories) > len(DEFAULT_COLORS):
        raise ValueError(
            f"implementation supports at most {len(DEFAULT_COLORS)} categories"
        )

    normalized: dict[tuple[str, str, str], float] = {}
    denominators: dict[str, float] = {}
    expected_categories = set(categories)
    for facet in facets:
        for sample in samples_by_facet[facet]:
            present = {
                category
                for current_facet, current_sample, category in values
                if current_facet == facet and current_sample == sample
            }
            if present != expected_categories:
                missing = sorted(expected_categories - present)
                extra = sorted(present - expected_categories)
                raise ValueError(
                    "CB-GRID-01 every sample must contain every category; "
                    f"facet={facet!r}, sample={sample!r}, "
                    f"missing={missing}, extra={extra}"
                )
            total = sum(values[(facet, sample, category)] for category in categories)
            denominator_key = f"{facet} | {sample}"
            denominators[denominator_key] = total
            if args.value_mode == "proportion":
                if abs(total - 1.0) > args.sum_tolerance:
                    raise ValueError(
                        "CB-DENOM-01 proportion rows must sum to one; "
                        f"{denominator_key} sums to {total:.12g}"
                    )
                for category in categories:
                    normalized[(facet, sample, category)] = values[
                        (facet, sample, category)
                    ]
            else:
                if total <= 0:
                    raise ValueError(
                        f"CB-DENOM-01 count denominator is zero for {denominator_key}"
                    )
                for category in categories:
                    normalized[(facet, sample, category)] = (
                        values[(facet, sample, category)] / total
                    )

    colors = split_list(args.colors) or list(DEFAULT_COLORS[: len(categories)])
    if len(colors) != len(categories):
        raise ValueError(
            "the number of --colors must equal the number of categories"
        )
    if any(not re.fullmatch(r"#[0-9A-Fa-f]{6}", color) for color in colors):
        raise ValueError("colors must use six-digit hexadecimal notation")
    if len({color.lower() for color in colors}) != len(colors):
        raise ValueError("each category must have a distinct color")

    label_mode = args.sample_labels
    show_labels = label_mode == "show" or (
        label_mode == "auto"
        and max(len(samples_by_facet[facet]) for facet in facets) <= 12
    )
    warnings: list[str] = []
    if label_mode == "auto" and not show_labels:
        warnings.append(
            "sample labels hidden automatically because at least one facet has more than 12 samples"
        )

    return {
        "path": path,
        "roles": roles,
        "rows": rows,
        "facets": facets,
        "categories": categories,
        "samples_by_facet": samples_by_facet,
        "values": normalized,
        "input_values": values,
        "records": records,
        "denominators": denominators,
        "colors": colors,
        "show_labels": show_labels,
        "warnings": warnings,
        "data_manifest": data_manifest,
    }
