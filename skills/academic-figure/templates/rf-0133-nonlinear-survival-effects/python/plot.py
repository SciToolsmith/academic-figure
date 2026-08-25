#!/usr/bin/env python3
"""Plot supplied exposure-effect curves without fitting or inference."""

from __future__ import annotations

import argparse
import csv
import math
import textwrap
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np


CURVE_FIELDS = (
    "facet",
    "group",
    "exposure",
    "effect",
    "ci_lower",
    "ci_upper",
    "reference_exposure",
    "reference_effect",
    "exposure_label",
    "effect_measure",
    "effect_scale",
    "interval_level",
    "interval_type",
)
ANNOTATION_FIELDS = ("facet", "group", "x", "y", "label")
COLORS = (
    "#2C6E9B",
    "#C05A47",
    "#4E8B57",
    "#8A63A8",
    "#C28B2C",
    "#3C8D91",
    "#9B5D73",
    "#6E6E6E",
)
LINESTYLES = ("-", "--", "-.", ":")


class ContractError(ValueError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize upstream supplied nonlinear effect curves; no model is fitted."
    )
    parser.add_argument("--input", required=True, help="Curve-grid CSV")
    parser.add_argument("--annotations", help="Optional supplied-annotation CSV")
    parser.add_argument("--output-prefix", required=True, help="Output path without extension")
    parser.add_argument("--title", default="Upstream nonlinear effect curves")
    parser.add_argument("--y-transform", choices=("linear", "log"), default="linear")
    parser.add_argument("--reference-tolerance", type=float, default=1e-6)
    parser.add_argument("--dpi", type=int, default=320)
    return parser.parse_args()


def read_csv(path: Path, required: Sequence[str]) -> List[Dict[str, str]]:
    if not path.is_file():
        raise ContractError(f"input file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        missing = [field for field in required if field not in fields]
        if missing:
            raise ContractError(f"{path.name} is missing required column(s): {', '.join(missing)}")
        rows = []
        for row_number, raw in enumerate(reader, start=2):
            row = {key: (value or "").strip() for key, value in raw.items()}
            row["__row_number__"] = str(row_number)
            rows.append(row)
    if not rows:
        raise ContractError(f"{path.name} contains no data rows")
    return rows


def finite_number(value: str, field: str, row_number: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise ContractError(f"row {row_number}: {field} must be numeric, got {value!r}") from exc
    if not math.isfinite(number):
        raise ContractError(f"row {row_number}: {field} must be finite")
    return number


def single_text(rows: Sequence[Mapping[str, object]], field: str) -> str:
    values = list(OrderedDict.fromkeys(str(row[field]) for row in rows))
    if len(values) != 1:
        raise ContractError(f"{field} must have one value across the full input; found {values}")
    if not values[0]:
        raise ContractError(f"{field} must not be empty")
    return values[0]


def close_enough(a: float, b: float, tolerance: float) -> bool:
    return abs(a - b) <= tolerance * max(1.0, abs(a), abs(b))


def validate_curves(
    raw_rows: Sequence[Dict[str, str]], tolerance: float, y_transform: str
) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ContractError("--reference-tolerance must be a finite positive number")

    rows: List[Dict[str, object]] = []
    numeric_fields = (
        "exposure",
        "effect",
        "ci_lower",
        "ci_upper",
        "reference_exposure",
        "reference_effect",
        "interval_level",
    )
    text_fields = ("facet", "group", "exposure_label", "effect_measure", "effect_scale", "interval_type")
    errors: List[str] = []
    for raw in raw_rows:
        row_number = raw["__row_number__"]
        for field in text_fields:
            if not raw[field]:
                errors.append(f"row {row_number}: {field} must not be empty")
        parsed: Dict[str, object] = dict(raw)
        for field in numeric_fields:
            try:
                parsed[field] = finite_number(raw[field], field, row_number)
            except ContractError as exc:
                errors.append(str(exc))
        if not errors or not any(error.startswith(f"row {row_number}:") for error in errors):
            lower = float(parsed["ci_lower"])
            effect = float(parsed["effect"])
            upper = float(parsed["ci_upper"])
            level = float(parsed["interval_level"])
            if not lower <= effect <= upper:
                errors.append(
                    f"row {row_number}: require ci_lower <= effect <= ci_upper, got {lower}, {effect}, {upper}"
                )
            if not 0 < level < 1:
                errors.append(f"row {row_number}: interval_level must be between 0 and 1")
        rows.append(parsed)
    if errors:
        detail = "\n  - ".join(errors[:20])
        suffix = "\n  - ..." if len(errors) > 20 else ""
        raise ContractError(f"curve input violates the data contract:\n  - {detail}{suffix}")

    effect_scale = single_text(rows, "effect_scale").lower()
    if effect_scale not in {"ratio", "difference"}:
        raise ContractError("effect_scale must be exactly 'ratio' or 'difference'")
    exposure_label = single_text(rows, "exposure_label")
    effect_measure = single_text(rows, "effect_measure")
    interval_type = single_text(rows, "interval_type")

    interval_levels = [float(row["interval_level"]) for row in rows]
    if max(interval_levels) - min(interval_levels) > 1e-12:
        raise ContractError("interval_level must have one numeric value across the full input")
    reference_effects = [float(row["reference_effect"]) for row in rows]
    if max(reference_effects) - min(reference_effects) > tolerance * max(
        1.0, max(abs(value) for value in reference_effects)
    ):
        raise ContractError("reference_effect must have one value across the full input")
    reference_effect = reference_effects[0]

    if effect_scale == "ratio":
        for row in rows:
            for field in ("effect", "ci_lower", "ci_upper", "reference_effect"):
                if float(row[field]) <= 0:
                    raise ContractError(
                        f"row {row['__row_number__']}: {field} must be > 0 for ratio scale"
                    )
    if y_transform == "log" and effect_scale != "ratio":
        raise ContractError("--y-transform log is allowed only when effect_scale=ratio")

    facets = list(OrderedDict.fromkeys(str(row["facet"]) for row in rows))
    groups = list(OrderedDict.fromkeys(str(row["group"]) for row in rows))
    if len(facets) > 9:
        raise ContractError(f"found {len(facets)} facets; the template limit is 9")
    if len(groups) > 8:
        raise ContractError(f"found {len(groups)} groups; the template limit is 8")
    if max(map(len, facets + groups)) > 80:
        raise ContractError("facet and group labels must be at most 80 characters")

    duplicate_keys = Counter(
        (str(row["facet"]), str(row["group"]), float(row["exposure"])) for row in rows
    )
    duplicate = next((key for key, count in duplicate_keys.items() if count > 1), None)
    if duplicate is not None:
        raise ContractError(f"duplicate (facet, group, exposure) key: {duplicate}")

    curves: "OrderedDict[Tuple[str, str], List[Dict[str, object]]]" = OrderedDict()
    for row in rows:
        curves.setdefault((str(row["facet"]), str(row["group"])), []).append(row)
    for key, curve in curves.items():
        curve.sort(key=lambda row: float(row["exposure"]))
        if len(curve) < 3:
            raise ContractError(f"curve {key} has {len(curve)} points; at least 3 are required")
        if len(curve) > 500:
            raise ContractError(f"curve {key} has {len(curve)} points; the limit is 500")
        refs = [float(row["reference_exposure"]) for row in curve]
        if max(refs) - min(refs) > tolerance * max(1.0, max(abs(value) for value in refs)):
            raise ContractError(f"curve {key} has inconsistent reference_exposure values")
        reference_x = refs[0]
        matches = [row for row in curve if close_enough(float(row["exposure"]), reference_x, tolerance)]
        if len(matches) != 1:
            raise ContractError(
                f"curve {key} reference_exposure={reference_x:g} must match exactly one supplied grid point"
            )
        if not close_enough(float(matches[0]["effect"]), reference_effect, tolerance):
            raise ContractError(
                f"curve {key} effect at reference exposure is {float(matches[0]['effect']):g}, "
                f"not reference_effect={reference_effect:g} within tolerance"
            )

    metadata: Dict[str, object] = {
        "facets": facets,
        "groups": groups,
        "curves": curves,
        "effect_scale": effect_scale,
        "effect_measure": effect_measure,
        "exposure_label": exposure_label,
        "interval_type": interval_type,
        "interval_level": interval_levels[0],
        "reference_effect": reference_effect,
    }
    return rows, metadata


def validate_annotations(
    raw_rows: Sequence[Dict[str, str]], curve_rows: Sequence[Mapping[str, object]], y_transform: str
) -> List[Dict[str, object]]:
    facet_order = list(OrderedDict.fromkeys(str(row["facet"]) for row in curve_rows))
    facet_groups = {
        facet: {str(row["group"]) for row in curve_rows if str(row["facet"]) == facet}
        for facet in facet_order
    }
    ranges = {}
    for facet in facet_order:
        selected = [row for row in curve_rows if str(row["facet"]) == facet]
        ranges[facet] = (
            min(float(row["exposure"]) for row in selected),
            max(float(row["exposure"]) for row in selected),
            min(float(row["ci_lower"]) for row in selected),
            max(float(row["ci_upper"]) for row in selected),
        )

    annotations: List[Dict[str, object]] = []
    counts: Counter[str] = Counter()
    for raw in raw_rows:
        row_number = raw["__row_number__"]
        facet, group, label = raw["facet"], raw["group"], raw["label"]
        if not facet or not label:
            raise ContractError(f"annotation row {row_number}: facet and label must not be empty")
        if facet not in facet_groups:
            raise ContractError(f"annotation row {row_number}: unknown facet {facet!r}")
        if group and group not in facet_groups[facet]:
            raise ContractError(
                f"annotation row {row_number}: group {group!r} does not occur in facet {facet!r}"
            )
        if len(label) > 90:
            raise ContractError(f"annotation row {row_number}: label exceeds 90 characters")
        x = finite_number(raw["x"], "x", row_number)
        y = finite_number(raw["y"], "y", row_number)
        xmin, xmax, ymin, ymax = ranges[facet]
        if not xmin <= x <= xmax:
            raise ContractError(
                f"annotation row {row_number}: x={x:g} is outside supplied facet range [{xmin:g}, {xmax:g}]"
            )
        if not ymin <= y <= ymax:
            raise ContractError(
                f"annotation row {row_number}: y={y:g} is outside supplied facet interval range [{ymin:g}, {ymax:g}]"
            )
        if y_transform == "log" and y <= 0:
            raise ContractError(f"annotation row {row_number}: y must be > 0 on a log axis")
        counts[facet] += 1
        if counts[facet] > 12:
            raise ContractError(f"facet {facet!r} has more than 12 supplied annotations")
        annotations.append({"facet": facet, "group": group, "x": x, "y": y, "label": label})
    return annotations


def plot_figure(
    rows: Sequence[Mapping[str, object]],
    metadata: Mapping[str, object],
    annotations: Sequence[Mapping[str, object]],
    title: str,
    y_transform: str,
) -> plt.Figure:
    facets = list(metadata["facets"])
    groups = list(metadata["groups"])
    curves = metadata["curves"]
    n_facets = len(facets)
    n_cols = 1 if n_facets == 1 else 2 if n_facets <= 4 else 3
    n_rows = math.ceil(n_facets / n_cols)
    legend_rows = math.ceil(len(groups) / min(4, len(groups)))
    width = min(16.5, 5.2 * n_cols)
    height = 3.6 * n_rows + 2.15 + 0.28 * legend_rows
    fig, axes = plt.subplots(
        n_rows,
        n_cols,
        figsize=(width, height),
        sharey=True,
        squeeze=False,
        constrained_layout=False,
    )
    fig.subplots_adjust(left=0.085, right=0.98, bottom=0.20, top=0.79, wspace=0.22, hspace=0.38)

    group_style = {
        group: (COLORS[index], LINESTYLES[index % len(LINESTYLES)])
        for index, group in enumerate(groups)
    }
    y_label = f"{metadata['effect_measure']} ({metadata['effect_scale']} scale)"
    all_axes = axes.ravel()
    for facet_index, facet in enumerate(facets):
        ax = all_axes[facet_index]
        facet_rows = [row for row in rows if str(row["facet"]) == facet]
        ax.axhline(
            float(metadata["reference_effect"]), color="#3F3F3F", linewidth=1.0, linestyle=(0, (3, 3)), zorder=1
        )
        reference_positions: List[float] = []
        for group in groups:
            key = (facet, group)
            if key not in curves:
                continue
            curve = curves[key]
            x = np.asarray([float(row["exposure"]) for row in curve])
            effect = np.asarray([float(row["effect"]) for row in curve])
            lower = np.asarray([float(row["ci_lower"]) for row in curve])
            upper = np.asarray([float(row["ci_upper"]) for row in curve])
            color, linestyle = group_style[group]
            ax.fill_between(x, lower, upper, color=color, alpha=0.16, linewidth=0, zorder=2)
            ax.plot(x, effect, color=color, linestyle=linestyle, linewidth=2.0, zorder=3)
            reference_x = float(curve[0]["reference_exposure"])
            reference_positions.append(reference_x)
            reference_row = min(curve, key=lambda row: abs(float(row["exposure"]) - reference_x))
            ax.scatter(
                [reference_x],
                [float(reference_row["effect"])],
                color=color,
                edgecolor="white",
                linewidth=0.8,
                marker="D",
                s=38,
                zorder=5,
            )
        unique_refs: List[float] = []
        for value in reference_positions:
            if not any(close_enough(value, existing, 1e-10) for existing in unique_refs):
                unique_refs.append(value)
        for reference_x in unique_refs:
            ax.axvline(reference_x, color="#777777", linewidth=0.8, linestyle=(0, (1, 3)), alpha=0.72, zorder=1)

        for annotation in annotations:
            if annotation["facet"] != facet:
                continue
            group = str(annotation["group"])
            color = group_style[group][0] if group else "#303030"
            ax.text(
                float(annotation["x"]),
                float(annotation["y"]),
                textwrap.fill(str(annotation["label"]), width=28),
                ha="left",
                va="center",
                fontsize=8.0,
                color=color,
                bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "edgecolor": color, "alpha": 0.88},
                zorder=6,
            )

        ax.set_title(textwrap.fill(facet, width=42), fontsize=11.5, fontweight="semibold", loc="left")
        ax.set_xlabel(str(metadata["exposure_label"]), fontsize=9.5)
        if facet_index % n_cols == 0:
            ax.set_ylabel(y_label, fontsize=9.5)
        if y_transform == "log":
            ax.set_yscale("log")
        ax.grid(axis="y", color="#D9D9D9", linewidth=0.6, alpha=0.7)
        ax.tick_params(labelsize=8.5)
        ax.spines[["top", "right"]].set_visible(False)
        ax.margins(x=0.04, y=0.12)

    for empty_index in range(n_facets, len(all_axes)):
        all_axes[empty_index].set_visible(False)

    handles = [
        Line2D([0], [0], color=group_style[group][0], linestyle=group_style[group][1], linewidth=2.2, label=group)
        for group in groups
    ]
    fig.suptitle(title, x=0.085, y=0.965, ha="left", fontsize=15, fontweight="bold")
    fig.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.905),
        ncol=min(4, len(handles)),
        frameon=False,
        fontsize=9,
        title="Group",
        title_fontsize=9,
    )
    interval_percent = 100 * float(metadata["interval_level"])
    caption = (
        f"Supplied {interval_percent:g}% {metadata['interval_type']} intervals; "
        "lines connect supplied grid points only. Diamonds and dotted vertical lines mark supplied reference exposures. "
        "No model fitting, smoothing, P values, or interval extrapolation."
    )
    fig.text(0.085, 0.035, textwrap.fill(caption, width=155), ha="left", va="bottom", fontsize=8, color="#555555")
    return fig


def main() -> None:
    args = parse_args()
    try:
        curve_rows_raw = read_csv(Path(args.input), CURVE_FIELDS)
        curve_rows, metadata = validate_curves(curve_rows_raw, args.reference_tolerance, args.y_transform)
        annotations: List[Dict[str, object]] = []
        if args.annotations:
            annotation_rows_raw = read_csv(Path(args.annotations), ANNOTATION_FIELDS)
            annotations = validate_annotations(annotation_rows_raw, curve_rows, args.y_transform)
        if args.dpi < 150 or args.dpi > 1200:
            raise ContractError("--dpi must be between 150 and 1200")
        figure = plot_figure(curve_rows, metadata, annotations, args.title, args.y_transform)
        prefix = Path(args.output_prefix)
        prefix.parent.mkdir(parents=True, exist_ok=True)
        png_path = prefix.with_suffix(".png")
        svg_path = prefix.with_suffix(".svg")
        figure.savefig(png_path, dpi=args.dpi, facecolor="white", bbox_inches="tight")
        figure.savefig(svg_path, facecolor="white", bbox_inches="tight")
        plt.close(figure)
    except ContractError as exc:
        raise SystemExit(f"ERROR: {exc}") from None

    curves = metadata["curves"]
    print(
        f"Loaded {len(curve_rows)} supplied grid rows: {len(curves)} curve(s), "
        f"{len(metadata['facets'])} facet(s), {len(metadata['groups'])} group(s); 0 rows excluded."
    )
    print(
        f"effect_measure={metadata['effect_measure']} | effect_scale={metadata['effect_scale']} | "
        f"reference_effect={float(metadata['reference_effect']):g} | "
        f"interval={100 * float(metadata['interval_level']):g}% {metadata['interval_type']} | "
        f"y_transform={args.y_transform}"
    )
    for (facet, group), curve in curves.items():
        print(
            f"facet={facet} | group={group} | supplied_points={len(curve)} | "
            f"exposure_range=[{float(curve[0]['exposure']):g}, {float(curve[-1]['exposure']):g}] | "
            f"reference_exposure={float(curve[0]['reference_exposure']):g} verified_on_grid=true"
        )
    print(f"supplied_annotations={len(annotations)}")
    print(f"Wrote {png_path}")
    print(f"Wrote {svg_path}")


if __name__ == "__main__":
    main()
