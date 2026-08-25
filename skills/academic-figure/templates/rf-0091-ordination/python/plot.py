#!/usr/bin/env python3
"""Plot validated, precomputed two-dimensional ordination coordinates."""

from __future__ import annotations

import argparse
import csv
import math
import sys
import textwrap
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D


TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = TEMPLATE_ROOT / "data"
MAX_GROUPS = 12
MAX_ANNOTATIONS = 3
MAX_ANNOTATION_LENGTH = 300
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "<", ">", "h", "p", "*"]


class ValidationError(Exception):
    pass


def read_table(
    path: Path, name: str, required: Sequence[str], allow_empty: bool = False
) -> Tuple[List[Dict[str, str]], List[str]]:
    if not path.is_file():
        raise ValidationError("{} file not found: {}".format(name, path))
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames
            if headers is None:
                raise ValidationError("{} has no CSV header".format(name))
            if any(header is None or header.strip() == "" for header in headers):
                raise ValidationError("{} contains an empty column name".format(name))
            if len(set(headers)) != len(headers):
                raise ValidationError("{} contains duplicate column names".format(name))
            missing = [column for column in required if column not in headers]
            if missing:
                raise ValidationError("{} is missing required columns: {}".format(name, ", ".join(missing)))
            rows: List[Dict[str, str]] = []
            for line, row in enumerate(reader, start=2):
                if None in row:
                    raise ValidationError("{} line {} has more values than header columns".format(name, line))
                clean = {key: (value or "").strip() for key, value in row.items()}
                clean["__line__"] = str(line)
                rows.append(clean)
    except UnicodeDecodeError as exc:
        raise ValidationError("{} must be UTF-8 CSV: {}".format(name, exc)) from exc
    if not rows and not allow_empty:
        raise ValidationError("{} must contain at least one data row".format(name))
    return rows, list(headers)


def finite_number(value: str, context: str) -> float:
    if value == "":
        raise ValidationError("{} cannot be empty".format(context))
    try:
        result = float(value)
    except ValueError as exc:
        raise ValidationError("{} must be numeric; got {!r}".format(context, value)) from exc
    if not math.isfinite(result):
        raise ValidationError("{} must be finite; got {!r}".format(context, value))
    return result


def provenance_declaration(
    name: str, rows: Sequence[Dict[str, str]], headers: Sequence[str]
) -> Optional[Tuple[str, str]]:
    has_status = "data_status" in headers
    has_seed = "simulation_seed" in headers
    if has_status != has_seed:
        raise ValidationError("{} must provide data_status and simulation_seed together".format(name))
    if not has_status or not rows:
        return None
    values = {(row["data_status"], row["simulation_seed"]) for row in rows}
    if any(not status or not seed for status, seed in values):
        raise ValidationError("{} has empty provenance values".format(name))
    if len(values) != 1:
        raise ValidationError("{} has inconsistent provenance values".format(name))
    return next(iter(values))


def validate_provenance(
    tables: Sequence[Tuple[str, Sequence[Dict[str, str]], Sequence[str]]]
) -> None:
    declarations = []
    for name, rows, headers in tables:
        value = provenance_declaration(name, rows, headers)
        if value is not None:
            declarations.append((name, value))
    if declarations:
        first_name, first_value = declarations[0]
        for name, value in declarations[1:]:
            if value != first_value:
                raise ValidationError(
                    "{} provenance {} does not match {} provenance {}".format(
                        name, value, first_name, first_value
                    )
                )


def validate_coordinates(
    rows: Sequence[Dict[str, str]], group_column: Optional[str], headers: Sequence[str]
) -> Tuple[np.ndarray, np.ndarray, List[str], Optional[List[str]]]:
    if group_column and group_column not in headers:
        raise ValidationError("Input is missing group column {!r}".format(group_column))
    sample_ids: List[str] = []
    groups: Optional[List[str]] = [] if group_column else None
    x_values: List[float] = []
    y_values: List[float] = []
    problems: List[str] = []
    for row in rows:
        line = row["__line__"]
        sample_id = row["sample_id"]
        if not sample_id:
            problems.append("line {} has an empty sample_id".format(line))
        sample_ids.append(sample_id)
        if groups is not None and group_column is not None:
            group = row[group_column]
            if not group:
                problems.append("line {} has an empty group".format(line))
            groups.append(group)
        try:
            x_values.append(finite_number(row["axis1"], "line {} axis1".format(line)))
            y_values.append(finite_number(row["axis2"], "line {} axis2".format(line)))
        except ValidationError as exc:
            problems.append(str(exc))
            x_values.append(float("nan"))
            y_values.append(float("nan"))
    duplicates = sorted({sample_id for sample_id in sample_ids if sample_id and sample_ids.count(sample_id) > 1})
    if duplicates:
        problems.append("duplicate sample_id values: {}".format(", ".join(duplicates[:10])))
    if groups is not None:
        levels = list(dict.fromkeys(groups))
        if len(levels) > MAX_GROUPS:
            problems.append("group column has {} levels; maximum is {}".format(len(levels), MAX_GROUPS))
        for level in levels:
            if level and groups.count(level) < 2:
                problems.append("group {!r} has fewer than 2 samples".format(level))
    if problems:
        shown = problems[:25]
        suffix = "\n  - ... additional errors omitted" if len(problems) > 25 else ""
        raise ValidationError("Coordinate validation failed:\n  - " + "\n  - ".join(shown) + suffix)
    x = np.asarray(x_values, dtype=float)
    y = np.asarray(y_values, dtype=float)
    if len(x) < 3:
        raise ValidationError("At least 3 coordinate rows are required")
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        raise ValidationError("axis1 and axis2 must each vary in the supplied coordinates")
    return x, y, sample_ids, groups


def validate_axis_metadata(rows: Sequence[Dict[str, str]]) -> Tuple[str, str, float, float]:
    if len(rows) != 2:
        raise ValidationError("axis metadata must contain exactly 2 rows: axis1 and axis2")
    by_key: Dict[str, Dict[str, str]] = {}
    for row in rows:
        key = row["axis_key"]
        if key not in {"axis1", "axis2"}:
            raise ValidationError("axis metadata uses unknown axis_key {!r}".format(key))
        if key in by_key:
            raise ValidationError("axis metadata duplicates axis_key {!r}".format(key))
        if not row["axis_label"]:
            raise ValidationError("axis metadata {} has an empty axis_label".format(key))
        by_key[key] = row
    if set(by_key) != {"axis1", "axis2"}:
        raise ValidationError("axis metadata must include axis1 and axis2 exactly once")
    variance1 = finite_number(by_key["axis1"]["explained_variance"], "axis1 explained_variance")
    variance2 = finite_number(by_key["axis2"]["explained_variance"], "axis2 explained_variance")
    for key, value in (("axis1", variance1), ("axis2", variance2)):
        if value < 0 or value > 1:
            raise ValidationError("{} explained_variance must be a 0-1 proportion".format(key))
    if variance1 + variance2 > 1.000001:
        raise ValidationError("axis1 + axis2 explained_variance cannot exceed 1")
    return by_key["axis1"]["axis_label"], by_key["axis2"]["axis_label"], variance1, variance2


def validate_annotations(rows: Sequence[Dict[str, str]]) -> List[str]:
    if len(rows) > MAX_ANNOTATIONS:
        raise ValidationError("At most {} supplied annotations are allowed".format(MAX_ANNOTATIONS))
    seen: set[str] = set()
    result: List[str] = []
    for row in rows:
        annotation_id = row["annotation_id"]
        text = row["annotation_text"]
        source = row["source_label"]
        if not annotation_id:
            raise ValidationError("supplied annotation has an empty annotation_id")
        if annotation_id in seen:
            raise ValidationError("supplied annotations duplicate ID {!r}".format(annotation_id))
        seen.add(annotation_id)
        if not text or not source:
            raise ValidationError("supplied annotation {} requires non-empty text and source".format(annotation_id))
        if len(text) > MAX_ANNOTATION_LENGTH:
            raise ValidationError(
                "supplied annotation {} exceeds {} characters".format(annotation_id, MAX_ANNOTATION_LENGTH)
            )
        result.append("SUPPLIED — {}: {}".format(source, text))
    return result


def expanded_limits(x: np.ndarray, y: np.ndarray) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    x_min, x_max = float(np.min(x)), float(np.max(x))
    y_min, y_max = float(np.min(y)), float(np.max(y))
    x_span = x_max - x_min
    y_span = y_max - y_min
    span = max(x_span, y_span) * 1.14
    x_mid = (x_min + x_max) / 2.0
    y_mid = (y_min + y_max) / 2.0
    return (x_mid - span / 2.0, x_mid + span / 2.0), (y_mid - span / 2.0, y_mid + span / 2.0)


def render(
    x: np.ndarray,
    y: np.ndarray,
    groups: Optional[Sequence[str]],
    axis_labels: Tuple[str, str],
    annotations: Sequence[str],
    output_prefix: Path,
    title: str,
    dpi: int,
) -> Tuple[Path, Path]:
    levels = list(dict.fromkeys(groups)) if groups is not None else ["All samples"]
    palette = plt.get_cmap("tab10" if len(levels) <= 10 else "tab20")
    colors = {level: palette(index % palette.N) for index, level in enumerate(levels)}
    group_array = np.asarray(groups if groups is not None else ["All samples"] * len(x), dtype=object)
    max_group_label = max(len(level) for level in levels)
    wrapped_annotations: List[str] = []
    for annotation in annotations:
        wrapped_annotations.extend(textwrap.wrap(annotation, width=108, subsequent_indent="  "))
    width = max(10.0, 10.2 + 0.035 * max_group_label)
    height = 8.3 + 0.18 * max(0, len(levels) - 3) + 0.24 * len(wrapped_annotations)
    fig = plt.figure(figsize=(width, height))
    grid = fig.add_gridspec(
        2, 2, width_ratios=[4.8, 1.55],
        height_ratios=[max(1.35, 0.55 + 0.24 * len(levels)), 4.6],
        left=0.13, right=0.97, bottom=0.13 + 0.018 * len(wrapped_annotations), top=0.87,
        wspace=0.08, hspace=0.08,
    )
    ax_top = fig.add_subplot(grid[0, 0])
    ax_main = fig.add_subplot(grid[1, 0])
    ax_right = fig.add_subplot(grid[1, 1])
    ax_empty = fig.add_subplot(grid[0, 1])
    ax_empty.axis("off")
    x_limits, y_limits = expanded_limits(x, y)
    point_size = max(20.0, min(54.0, 1700.0 / len(x)))

    for index, level in enumerate(levels):
        selected = group_array == level
        ax_main.scatter(
            x[selected], y[selected], s=point_size, marker=MARKERS[index],
            facecolor=colors[level], edgecolor="white", linewidth=0.65, alpha=0.84,
            label=level, zorder=3,
        )
    if x_limits[0] <= 0 <= x_limits[1]:
        ax_main.axvline(0, color="#9CA3AF", linestyle="--", linewidth=0.8, zorder=0)
    if y_limits[0] <= 0 <= y_limits[1]:
        ax_main.axhline(0, color="#9CA3AF", linestyle="--", linewidth=0.8, zorder=0)
    ax_main.grid(color="#E5E7EB", linewidth=0.65, zorder=0)
    ax_main.set_xlim(*x_limits)
    ax_main.set_ylim(*y_limits)
    ax_main.set_aspect("equal", adjustable="box")
    ax_main.set_xlabel(axis_labels[0])
    ax_main.set_ylabel(axis_labels[1])
    ax_main.spines["top"].set_visible(False)
    ax_main.spines["right"].set_visible(False)
    if groups is not None:
        ax_main.legend(
            loc="best", frameon=True, framealpha=0.9, fontsize=8.2,
            ncol=1 if len(levels) <= 6 else 2,
        )

        x_sets = [x[group_array == level] for level in levels]
        y_sets = [y[group_array == level] for level in levels]
        top_boxes = ax_top.boxplot(
            x_sets, vert=False, patch_artist=True, widths=0.62,
            showfliers=False, medianprops={"color": "#111827", "linewidth": 1.0},
        )
        ax_top.set_yticks(range(1, len(levels) + 1))
        ax_top.set_yticklabels(levels)
        for box, level in zip(top_boxes["boxes"], levels):
            box.set_facecolor(colors[level])
            box.set_alpha(0.62)
        right_boxes = ax_right.boxplot(
            y_sets, vert=True, patch_artist=True, widths=0.62,
            showfliers=False, medianprops={"color": "#111827", "linewidth": 1.0},
        )
        ax_right.set_xticks(range(1, len(levels) + 1))
        ax_right.set_xticklabels([""] * len(levels))
        for box, level in zip(right_boxes["boxes"], levels):
            box.set_facecolor(colors[level])
            box.set_alpha(0.62)
        ax_top.set_ylabel("Group", fontsize=8)
        ax_right.set_xlabel("Groups", fontsize=8)
    else:
        bins = max(7, min(20, int(math.ceil(math.sqrt(len(x))))))
        ax_top.hist(x, bins=bins, color=colors["All samples"], alpha=0.62, edgecolor="white")
        ax_right.hist(y, bins=bins, orientation="horizontal", color=colors["All samples"], alpha=0.62, edgecolor="white")

    ax_top.set_xlim(*x_limits)
    ax_top.tick_params(axis="x", labelbottom=False)
    ax_top.tick_params(axis="y", labelsize=max(6.3, 8.2 - 0.12 * max_group_label))
    ax_top.set_title("Axis 1 distribution by group" if groups is not None else "Axis 1 distribution", fontsize=9)
    ax_top.spines["top"].set_visible(False)
    ax_top.spines["right"].set_visible(False)
    ax_right.set_ylim(*y_limits)
    ax_right.tick_params(axis="y", labelleft=False)
    ax_right.tick_params(axis="x", labelbottom=False)
    ax_right.set_title("Axis 2\nby group" if groups is not None else "Axis 2\ndistribution", fontsize=9)
    ax_right.spines["top"].set_visible(False)
    ax_right.spines["right"].set_visible(False)

    fig.suptitle(title, y=0.968, fontsize=14, fontweight="semibold")
    subtitle = "Precomputed coordinates supplied; n = {}; groups = {}".format(
        len(x), len(levels) if groups is not None else 0
    )
    fig.text(0.5, 0.935, subtitle, ha="center", va="top", fontsize=9, color="#374151")
    footer_y = 0.025
    fig.text(
        0.5, footer_y, "Plotting only: no ordination, PERMANOVA, or statistical conclusion was computed or verified.",
        ha="center", va="bottom", fontsize=8, color="#4B5563",
    )
    for line in reversed(wrapped_annotations):
        footer_y += 0.020
        fig.text(0.13, footer_y, line, ha="left", va="bottom", fontsize=7.7, color="#7C2D12")

    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    png_path = Path(str(output_prefix) + ".png")
    svg_path = Path(str(output_prefix) + ".svg")
    fig.savefig(png_path, dpi=dpi, facecolor="white", metadata={"Software": "rf-0091 plot.py"})
    fig.savefig(svg_path, facecolor="white", metadata={"Creator": "rf-0091 plot.py"})
    plt.close(fig)
    return png_path, svg_path


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Plot supplied precomputed ordination coordinates without recomputing ordination or tests.")
    result.add_argument("--input", type=Path, default=DATA_DIR / "simulated_fixed_seed_ordination.csv")
    result.add_argument("--group-column")
    result.add_argument("--axis-metadata", type=Path)
    result.add_argument("--supplied-annotations", type=Path)
    result.add_argument("--output-prefix", type=Path, required=True)
    result.add_argument("--title", default="Precomputed ordination")
    result.add_argument("--dpi", type=int, default=320)
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if args.dpi < 300 or args.dpi > 1200:
        raise ValidationError("--dpi must be an integer from 300 to 1200")
    if args.output_prefix.suffix.lower() in {".png", ".svg", ".pdf"}:
        raise ValidationError("--output-prefix must not include .png, .svg, or .pdf")
    coordinate_rows, coordinate_headers = read_table(
        args.input, "coordinates", ["sample_id", "axis1", "axis2"]
    )
    provenance_tables: List[Tuple[str, Sequence[Dict[str, str]], Sequence[str]]] = [
        ("coordinates", coordinate_rows, coordinate_headers)
    ]
    axis_labels = ("Axis 1", "Axis 2")
    axis_metadata_rows: List[Dict[str, str]] = []
    if args.axis_metadata is not None:
        axis_metadata_rows, axis_headers = read_table(
            args.axis_metadata, "axis metadata",
            ["axis_key", "axis_label", "explained_variance"],
        )
        provenance_tables.append(("axis metadata", axis_metadata_rows, axis_headers))
        label1, label2, variance1, variance2 = validate_axis_metadata(axis_metadata_rows)
        axis_labels = (
            "{} ({:.1%})".format(label1, variance1),
            "{} ({:.1%})".format(label2, variance2),
        )
    annotations: List[str] = []
    if args.supplied_annotations is not None:
        annotation_rows, annotation_headers = read_table(
            args.supplied_annotations, "supplied annotations",
            ["annotation_id", "annotation_text", "source_label"],
        )
        provenance_tables.append(("supplied annotations", annotation_rows, annotation_headers))
        annotations = validate_annotations(annotation_rows)
    validate_provenance(provenance_tables)
    x, y, _, groups = validate_coordinates(coordinate_rows, args.group_column, coordinate_headers)
    png_path, svg_path = render(
        x, y, groups, axis_labels, annotations, args.output_prefix, args.title, args.dpi
    )
    print("Validated {} unique samples; missing coordinates: 0; group levels: {}.".format(
        len(x), len(set(groups)) if groups is not None else 0
    ))
    print("Coordinates were treated as precomputed; ordination and statistical tests computed: 0.")
    print("Axis metadata supplied: {}; supplied annotations displayed: {} (not statistically verified).".format(
        "yes" if args.axis_metadata is not None else "no", len(annotations)
    ))
    print("Wrote {}".format(png_path))
    print("Wrote {}".format(svg_path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValidationError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        sys.exit(2)
