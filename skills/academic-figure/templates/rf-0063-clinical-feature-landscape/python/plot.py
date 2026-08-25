#!/usr/bin/env python3
"""Render a feature-spec-driven mixed clinical feature matrix."""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, to_rgba
from matplotlib.patches import Rectangle


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MISSING = {"", "NA"}
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
INT_RE = re.compile(r"^[0-9]+$")
MAX_SAMPLES = 60
MAX_FEATURES = 16


class ValidationError(Exception):
    pass


def read_table(path: Path, name: str, required: Sequence[str]) -> Tuple[List[Dict[str, str]], List[str]]:
    if not path.is_file():
        raise ValidationError("{} file not found: {}".format(name, path))
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames
            if headers is None:
                raise ValidationError("{} has no CSV header".format(name))
            if any(header is None or not header.strip() for header in headers):
                raise ValidationError("{} contains an empty column name".format(name))
            if len(set(headers)) != len(headers):
                raise ValidationError("{} contains duplicate column names".format(name))
            missing = [column for column in required if column not in headers]
            if missing:
                raise ValidationError("{} is missing columns: {}".format(name, ", ".join(missing)))
            rows: List[Dict[str, str]] = []
            for line, row in enumerate(reader, start=2):
                if None in row:
                    raise ValidationError("{} line {} has extra values".format(name, line))
                clean = {key: (value or "").strip() for key, value in row.items()}
                clean["__line__"] = str(line)
                rows.append(clean)
    except UnicodeDecodeError as exc:
        raise ValidationError("{} must be UTF-8 CSV: {}".format(name, exc)) from exc
    if not rows:
        raise ValidationError("{} must contain at least one row".format(name))
    return rows, list(headers)


def finite(value: str, context: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise ValidationError("{} must be numeric; got {!r}".format(context, value)) from exc
    if not math.isfinite(result):
        raise ValidationError("{} must be finite; got {!r}".format(context, value))
    return result


def positive_integer(value: str, context: str) -> int:
    if not INT_RE.fullmatch(value) or int(value) < 1:
        raise ValidationError("{} must be a positive integer".format(context))
    return int(value)


def split_pipe(value: str, context: str) -> List[str]:
    items = [item.strip() for item in value.split("|")]
    if any(not item for item in items):
        raise ValidationError("{} contains an empty pipe-delimited item".format(context))
    if len(set(items)) != len(items):
        raise ValidationError("{} contains duplicate items".format(context))
    return items


def provenance(name: str, rows: Sequence[Dict[str, str]], headers: Sequence[str]) -> Optional[Tuple[str, str]]:
    has_status = "data_status" in headers
    has_seed = "simulation_seed" in headers
    if has_status != has_seed:
        raise ValidationError("{} must provide data_status and simulation_seed together".format(name))
    if not has_status:
        return None
    values = {(row["data_status"], row["simulation_seed"]) for row in rows}
    if any(not status or not seed for status, seed in values) or len(values) != 1:
        raise ValidationError("{} provenance must be non-empty and consistent".format(name))
    return next(iter(values))


def validate_specs(rows: Sequence[Dict[str, str]]) -> List[Dict[str, object]]:
    if len(rows) > MAX_FEATURES:
        raise ValidationError("At most {} features can be rendered; received {}".format(MAX_FEATURES, len(rows)))
    specs: List[Dict[str, object]] = []
    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    for row in rows:
        line = row["__line__"]
        feature_id = row["feature_id"]
        if not feature_id:
            raise ValidationError("feature spec line {} has an empty feature_id".format(line))
        if feature_id in seen_ids:
            raise ValidationError("feature spec duplicates feature_id {!r}".format(feature_id))
        seen_ids.add(feature_id)
        if not row["feature_label"]:
            raise ValidationError("feature {} has an empty feature_label".format(feature_id))
        feature_type = row["feature_type"]
        if feature_type not in {"continuous", "categorical", "binary"}:
            raise ValidationError("feature {} has unsupported type {!r}".format(feature_id, feature_type))
        order = positive_integer(row["display_order"], "feature {} display_order".format(feature_id))
        if order in seen_orders:
            raise ValidationError("feature spec duplicates display_order {}".format(order))
        seen_orders.add(order)
        if not row["missing_label"] or not COLOR_RE.fullmatch(row["missing_color"]):
            raise ValidationError("feature {} needs a missing label and #RRGGBB missing color".format(feature_id))
        colors = split_pipe(row["colors"], "feature {} colors".format(feature_id))
        if any(not COLOR_RE.fullmatch(color) for color in colors):
            raise ValidationError("feature {} colors must use #RRGGBB".format(feature_id))
        if row["missing_color"].lower() in {color.lower() for color in colors}:
            raise ValidationError("feature {} missing color must differ from observed colors".format(feature_id))
        levels: List[str] = []
        display_min: Optional[float] = None
        display_max: Optional[float] = None
        if feature_type == "continuous":
            if row["display_min"] == "" or row["display_max"] == "":
                raise ValidationError("continuous feature {} requires display_min and display_max".format(feature_id))
            display_min = finite(row["display_min"], "feature {} display_min".format(feature_id))
            display_max = finite(row["display_max"], "feature {} display_max".format(feature_id))
            if not display_min < display_max:
                raise ValidationError("feature {} requires display_min < display_max".format(feature_id))
            if row["levels"]:
                raise ValidationError("continuous feature {} must leave levels empty".format(feature_id))
            if len(colors) != 2:
                raise ValidationError("continuous feature {} requires exactly two endpoint colors".format(feature_id))
        else:
            if row["display_min"] or row["display_max"]:
                raise ValidationError("{} feature {} must leave display bounds empty".format(feature_type, feature_id))
            levels = split_pipe(row["levels"], "feature {} levels".format(feature_id))
            if feature_type == "binary" and len(levels) != 2:
                raise ValidationError("binary feature {} requires exactly two levels".format(feature_id))
            if feature_type == "categorical" and not 2 <= len(levels) <= 8:
                raise ValidationError("categorical feature {} requires 2-8 levels".format(feature_id))
            if len(colors) != len(levels):
                raise ValidationError("feature {} needs one color per level".format(feature_id))
        specs.append(
            {
                "feature_id": feature_id,
                "feature_label": row["feature_label"],
                "feature_type": feature_type,
                "display_order": order,
                "display_min": display_min,
                "display_max": display_max,
                "levels": levels,
                "colors": colors,
                "missing_label": row["missing_label"],
                "missing_color": row["missing_color"],
            }
        )
    specs.sort(key=lambda item: int(item["display_order"]))
    return specs


def validate_samples(
    rows: Sequence[Dict[str, str]], headers: Sequence[str], specs: Sequence[Dict[str, object]]
) -> Tuple[List[Dict[str, object]], int]:
    if len(rows) > MAX_SAMPLES:
        raise ValidationError("At most {} samples can be rendered; received {}".format(MAX_SAMPLES, len(rows)))
    missing_columns = [str(spec["feature_id"]) for spec in specs if spec["feature_id"] not in headers]
    if missing_columns:
        raise ValidationError("samples is missing feature columns: {}".format(", ".join(missing_columns)))
    parsed: List[Dict[str, object]] = []
    ids: set[str] = set()
    orders: set[int] = set()
    missing_count = 0
    for row in rows:
        line = row["__line__"]
        sample_id = row["sample_id"]
        if not sample_id or sample_id in ids:
            raise ValidationError("samples line {} has an empty or duplicate sample_id {!r}".format(line, sample_id))
        ids.add(sample_id)
        if not row["sample_label"]:
            raise ValidationError("sample {} has an empty sample_label".format(sample_id))
        order = positive_integer(row["display_order"], "sample {} display_order".format(sample_id))
        if order in orders:
            raise ValidationError("samples duplicates display_order {}".format(order))
        orders.add(order)
        values: Dict[str, object] = {}
        for spec in specs:
            feature_id = str(spec["feature_id"])
            raw = row[feature_id]
            if raw in MISSING:
                values[feature_id] = None
                missing_count += 1
                continue
            if spec["feature_type"] == "continuous":
                number = finite(raw, "sample {} feature {}".format(sample_id, feature_id))
                if number < float(spec["display_min"]) or number > float(spec["display_max"]):
                    raise ValidationError(
                        "sample {} feature {} value {} lies outside [{}, {}]".format(
                            sample_id, feature_id, number, spec["display_min"], spec["display_max"]
                        )
                    )
                values[feature_id] = number
            else:
                levels = list(spec["levels"])
                if raw not in levels:
                    raise ValidationError("sample {} feature {} has unknown level {!r}".format(sample_id, feature_id, raw))
                values[feature_id] = raw
        parsed.append(
            {"sample_id": sample_id, "sample_label": row["sample_label"], "display_order": order, "values": values}
        )
    parsed.sort(key=lambda item: int(item["display_order"]))
    return parsed, missing_count


def cell_color(value: object, spec: Dict[str, object]) -> str:
    if value is None:
        return str(spec["missing_color"])
    if spec["feature_type"] == "continuous":
        fraction = (float(value) - float(spec["display_min"])) / (float(spec["display_max"]) - float(spec["display_min"]))
        cmap = LinearSegmentedColormap.from_list("feature", list(spec["colors"]))
        return matplotlib.colors.to_hex(cmap(fraction), keep_alpha=False)
    mapping = dict(zip(spec["levels"], spec["colors"]))
    return str(mapping[value])


def render(
    samples: Sequence[Dict[str, object]], specs: Sequence[Dict[str, object]], output_prefix: Path, title: str, dpi: int
) -> Tuple[Path, Path]:
    n_samples = len(samples)
    n_features = len(specs)
    sample_labels = ["{} [{}]".format(item["sample_label"], item["sample_id"]) for item in samples]
    max_sample_chars = max(len(label) for label in sample_labels)
    max_feature_chars = max(len(str(spec["feature_label"])) for spec in specs)
    max_level_chars = max([len(level) for spec in specs for level in spec["levels"]] or [0])
    width = max(12.0, 6.4 + 0.72 * n_features + 0.04 * (max_sample_chars + max_feature_chars + max_level_chars))
    height = max(7.0, 2.8 + 0.34 * n_samples)
    fig = plt.figure(figsize=(width, height))
    grid = fig.add_gridspec(1, 2, width_ratios=[max(4.0, n_features), 5.0], left=0.13, right=0.98, bottom=0.11, top=0.88, wspace=0.18)
    ax = fig.add_subplot(grid[0, 0])
    legend_ax = fig.add_subplot(grid[0, 1])

    for row_index, sample in enumerate(samples):
        values = sample["values"]
        for column_index, spec in enumerate(specs):
            value = values[str(spec["feature_id"])]
            rectangle = Rectangle(
                (column_index - 0.5, row_index - 0.5), 1, 1,
                facecolor=cell_color(value, spec), edgecolor="white", linewidth=0.8,
                hatch="////" if value is None else None,
            )
            ax.add_patch(rectangle)
    ax.set_xlim(-0.5, n_features - 0.5)
    ax.set_ylim(-0.5, n_samples - 0.5)
    ax.invert_yaxis()
    ax.set_xticks(range(n_features))
    ax.set_xticklabels([str(spec["feature_label"]) for spec in specs], rotation=35, ha="left", fontsize=8.2)
    ax.xaxis.tick_top()
    ax.set_yticks(range(n_samples))
    ax.set_yticklabels(sample_labels, fontsize=max(6.2, 8.4 - 0.035 * max_sample_chars))
    ax.tick_params(length=0, pad=5)
    for spine in ax.spines.values():
        spine.set_visible(False)

    legend_ax.set_xlim(0, 1)
    legend_ax.set_ylim(0, n_features + 1.35)
    legend_ax.axis("off")
    for index, spec in enumerate(specs):
        y = n_features - index + 0.30
        legend_ax.text(0.01, y + 0.24, "{} [{}]".format(spec["feature_label"], spec["feature_type"]),
                       ha="left", va="center", fontsize=8.2, fontweight="semibold")
        if spec["feature_type"] == "continuous":
            cmap = LinearSegmentedColormap.from_list("legend", list(spec["colors"]))
            for step in range(32):
                legend_ax.add_patch(Rectangle((0.04 + 0.015 * step, y - 0.10), 0.016, 0.19,
                                              facecolor=cmap(step / 31), edgecolor="none"))
            legend_ax.text(0.03, y - 0.20, "{:g}".format(float(spec["display_min"])), fontsize=7, ha="left")
            legend_ax.text(0.53, y - 0.20, "{:g}".format(float(spec["display_max"])), fontsize=7, ha="right")
        else:
            levels = list(spec["levels"])
            colors = list(spec["colors"])
            slot = 0.88 / len(levels)
            for level_index, (level, color) in enumerate(zip(levels, colors)):
                x = 0.03 + level_index * slot
                legend_ax.add_patch(Rectangle((x, y - 0.10), 0.035, 0.19, facecolor=color, edgecolor="#4B5563", linewidth=0.4))
                legend_ax.text(x + 0.045, y, level, fontsize=max(6.3, 7.4 - 0.04 * len(level)), va="center", ha="left")
    missing_pairs = list(dict.fromkeys((str(spec["missing_label"]), str(spec["missing_color"])) for spec in specs))
    missing_y = 0.35
    legend_ax.text(0.01, missing_y + 0.32, "Missing encoding", fontsize=8.2, fontweight="semibold")
    for index, (label, color) in enumerate(missing_pairs):
        x = 0.04 + index * 0.30
        legend_ax.add_patch(Rectangle((x, missing_y - 0.04), 0.06, 0.20, facecolor=color,
                                      edgecolor="#4B5563", linewidth=0.5, hatch="////"))
        legend_ax.text(x + 0.075, missing_y + 0.06, label, va="center", fontsize=7.2)

    fig.suptitle(title, y=0.975, fontsize=14, fontweight="semibold")
    fig.text(0.5, 0.94, "Feature types and scales supplied explicitly; sample order from input display_order.",
             ha="center", va="top", fontsize=9, color="#374151")
    fig.text(0.5, 0.018, "Missing is encoded separately and never treated as zero; no clustering or inference is performed.",
             ha="center", va="bottom", fontsize=8, color="#4B5563")
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    png = Path(str(output_prefix) + ".png")
    svg = Path(str(output_prefix) + ".svg")
    fig.savefig(png, dpi=dpi, facecolor="white", metadata={"Software": "rf-0063 plot.py"})
    fig.savefig(svg, facecolor="white", metadata={"Creator": "rf-0063 plot.py"})
    plt.close(fig)
    return png, svg


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Draw a feature-spec-driven mixed feature matrix.")
    result.add_argument("--samples", type=Path, default=DATA_DIR / "simulated_fixed_seed_samples.csv")
    result.add_argument("--feature-spec", type=Path, default=DATA_DIR / "simulated_fixed_seed_feature_spec.csv")
    result.add_argument("--output-prefix", type=Path, required=True)
    result.add_argument("--title", default="Mixed feature landscape")
    result.add_argument("--dpi", type=int, default=320)
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if args.dpi < 300 or args.dpi > 1200:
        raise ValidationError("--dpi must be an integer from 300 to 1200")
    if args.output_prefix.suffix.lower() in {".png", ".svg", ".pdf"}:
        raise ValidationError("--output-prefix must not include an extension")
    spec_rows, spec_headers = read_table(
        args.feature_spec, "feature spec",
        ["feature_id", "feature_label", "feature_type", "display_order", "display_min", "display_max",
         "levels", "colors", "missing_label", "missing_color"],
    )
    sample_rows, sample_headers = read_table(
        args.samples, "samples", ["sample_id", "sample_label", "display_order"]
    )
    spec_provenance = provenance("feature spec", spec_rows, spec_headers)
    sample_provenance = provenance("samples", sample_rows, sample_headers)
    if spec_provenance is not None and sample_provenance is not None and spec_provenance != sample_provenance:
        raise ValidationError("samples and feature spec provenance do not match")
    specs = validate_specs(spec_rows)
    samples, missing_count = validate_samples(sample_rows, sample_headers, specs)
    png, svg = render(samples, specs, args.output_prefix, args.title, args.dpi)
    type_counts = {kind: sum(spec["feature_type"] == kind for spec in specs) for kind in ("continuous", "categorical", "binary")}
    print("Validated {} unique samples and {} features; missing cells: {}; invalid rows excluded: 0.".format(
        len(samples), len(specs), missing_count
    ))
    print("Feature types: continuous={}, categorical={}, binary={}.".format(
        type_counts["continuous"], type_counts["categorical"], type_counts["binary"]
    ))
    print("Sample order source: input display_order; clustering/reordering performed: no.")
    print("Wrote {}".format(png))
    print("Wrote {}".format(svg))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValidationError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        sys.exit(2)
