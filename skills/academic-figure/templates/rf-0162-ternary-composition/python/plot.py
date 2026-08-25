#!/usr/bin/env python3
"""Render a validated three-part composition as one or more ternary panels."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "simulated_fixed_seed_demo.csv"
SQRT3_OVER_2 = math.sqrt(3.0) / 2.0
PALETTE = [
    "#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9",
    "#6A3D9A", "#8C6D31", "#1B9E77", "#7570B3", "#E7298A", "#66A61E",
    "#A6761D", "#1F78B4", "#B15928", "#4D4D4D",
]
MARKERS = ["o", "s", "^", "D", "P", "X", "v", "<", ">", "h", "*", "p"]


class ContractError(ValueError):
    """Raised when the input violates the public data contract."""


@dataclass(frozen=True)
class Row:
    sample_id: str
    a: float
    b: float
    c: float
    group: str
    facet: str
    label: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-prefix", type=Path, default=Path.cwd() / "ternary_python")
    parser.add_argument("--title", default="Three-part compositions")
    parser.add_argument("--component-labels", default="Component A,Component B,Component C")
    parser.add_argument("--sum-target", type=float, default=1.0)
    parser.add_argument("--sum-tolerance", type=float, default=1e-6)
    parser.add_argument("--normalize", action="store_true")
    parser.add_argument("--dpi", type=int, default=320)
    return parser.parse_args()


def ordered_unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def parse_finite(raw: str, field: str, row_number: int) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"row {row_number}: {field} must be numeric") from exc
    if not math.isfinite(value):
        raise ContractError(f"row {row_number}: {field} must be finite")
    return value


def load_rows(path: Path, normalize: bool, target: float, tolerance: float) -> tuple[list[Row], str | None]:
    if not path.is_file():
        raise ContractError(f"input CSV does not exist: {path}")
    if not math.isfinite(target) or target <= 0:
        raise ContractError("--sum-target must be a positive finite number")
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ContractError("--sum-tolerance must be a nonnegative finite number")

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        required = {"sample_id", "component_a", "component_b", "component_c"}
        missing = sorted(required.difference(headers))
        if missing:
            raise ContractError("missing required column(s): " + ", ".join(missing))
        raw_rows = list(reader)
    if not raw_rows:
        raise ContractError("input CSV has no data rows")

    has_source_type = "source_type" in headers
    has_source_seed = "source_seed" in headers
    if has_source_type != has_source_seed:
        raise ContractError("source_type and source_seed must be supplied together")

    rows: list[Row] = []
    ids: set[str] = set()
    provenance: set[tuple[str, str]] = set()
    for row_number, raw in enumerate(raw_rows, start=2):
        sample_id = (raw.get("sample_id") or "").strip()
        if not sample_id:
            raise ContractError(f"row {row_number}: sample_id must not be empty")
        if sample_id in ids:
            raise ContractError(f"row {row_number}: duplicate sample_id {sample_id!r}")
        ids.add(sample_id)
        values = [
            parse_finite(raw.get("component_a", ""), "component_a", row_number),
            parse_finite(raw.get("component_b", ""), "component_b", row_number),
            parse_finite(raw.get("component_c", ""), "component_c", row_number),
        ]
        if any(value < 0 for value in values):
            raise ContractError(f"row {row_number}: components must be nonnegative")
        total = sum(values)
        if total <= 0:
            raise ContractError(f"row {row_number}: component total must be positive")
        if normalize:
            values = [value / total for value in values]
        else:
            if abs(total - target) > tolerance:
                raise ContractError(
                    f"row {row_number}: component sum is {total:.12g}, expected {target:.12g} "
                    f"± {tolerance:.3g}; use --normalize only when scientifically intended"
                )
            values = [value / target for value in values]
        group = (raw.get("group") or "All samples").strip()
        facet = (raw.get("facet") or "Composition").strip()
        label = (raw.get("label") or "").strip()
        if not group or not facet:
            raise ContractError(f"row {row_number}: group and facet must not be empty when supplied")
        if has_source_type:
            source_type = (raw.get("source_type") or "").strip()
            source_seed = (raw.get("source_seed") or "").strip()
            if not source_type or not source_seed:
                raise ContractError(f"row {row_number}: provenance fields must not be empty")
            provenance.add((source_type, source_seed))
        rows.append(Row(sample_id, values[0], values[1], values[2], group, facet, label))

    provenance_note: str | None = None
    if provenance:
        if len(provenance) != 1:
            raise ContractError("source_type/source_seed must be constant across the file")
        source_type, source_seed = next(iter(provenance))
        if source_type.lower() == "simulated":
            try:
                if int(source_seed) <= 0:
                    raise ValueError
            except ValueError as exc:
                raise ContractError("simulated data require one positive integer source_seed") from exc
            provenance_note = f"SIMULATED DEMONSTRATION DATA · fixed seed {source_seed}"
        else:
            provenance_note = f"Declared source: {source_type}"
    return rows, provenance_note


def ternary_xy(row: Row) -> tuple[float, float]:
    return row.b + 0.5 * row.c, SQRT3_OVER_2 * row.c


def draw_triangle(ax: plt.Axes, labels: list[str]) -> None:
    edge = "#31383D"
    grid = "#DCE2E1"
    vertices_x = [0.0, 1.0, 0.5, 0.0]
    vertices_y = [0.0, 0.0, SQRT3_OVER_2, 0.0]
    ax.plot(vertices_x, vertices_y, color=edge, linewidth=1.05, zorder=2)
    for fraction in (0.25, 0.5, 0.75):
        # constant A
        c0, c1 = 1.0 - fraction, 0.0
        ax.plot([0.5 * c0, 1.0 - fraction], [SQRT3_OVER_2 * c0, 0.0], color=grid, lw=0.65, zorder=0)
        # constant B
        ax.plot([fraction + 0.5 * (1.0 - fraction), fraction], [SQRT3_OVER_2 * (1.0 - fraction), 0.0], color=grid, lw=0.65, zorder=0)
        # constant C
        ax.plot([0.5 * fraction, 1.0 - 0.5 * fraction], [SQRT3_OVER_2 * fraction] * 2, color=grid, lw=0.65, zorder=0)
    ax.text(0.025, 0.025, labels[0], ha="left", va="bottom", fontsize=8.2, fontweight="semibold")
    ax.text(0.975, 0.025, labels[1], ha="right", va="bottom", fontsize=8.2, fontweight="semibold")
    ax.text(0.5, SQRT3_OVER_2 + 0.035, labels[2], ha="center", va="bottom", fontsize=8.6, fontweight="semibold")
    ax.set_xlim(-0.11, 1.11)
    ax.set_ylim(-0.09, SQRT3_OVER_2 + 0.10)
    ax.set_aspect("equal")
    ax.axis("off")


def main() -> int:
    args = parse_args()
    labels = [part.strip() for part in args.component_labels.split(",")]
    if len(labels) != 3 or any(not part for part in labels):
        raise ContractError("--component-labels must contain exactly three nonempty comma-separated labels")
    if args.dpi < 150 or args.dpi > 1200:
        raise ContractError("--dpi must be between 150 and 1200")
    rows, provenance_note = load_rows(args.input, args.normalize, args.sum_target, args.sum_tolerance)
    facets = ordered_unique(row.facet for row in rows)
    groups = ordered_unique(row.group for row in rows)
    labels_count = sum(bool(row.label) for row in rows)
    if len(facets) > 9:
        raise ContractError(f"{len(facets)} facets exceed the readable single-figure limit of 9")
    if len(groups) > 16:
        raise ContractError(f"{len(groups)} groups exceed the supported color/marker combinations (16)")
    if labels_count > 18:
        raise ContractError(f"{labels_count} labels exceed the readable single-figure limit of 18")

    ncols = min(3, len(facets))
    nrows = math.ceil(len(facets) / ncols)
    width = max(5.8, 4.25 * ncols)
    height = 1.35 + 3.9 * nrows + (0.45 if len(groups) > 1 else 0.0)
    fig, axes = plt.subplots(nrows, ncols, figsize=(width, height), squeeze=False)
    fig.patch.set_facecolor("#FBFAF7")
    style = {
        group: (PALETTE[index], MARKERS[index % len(MARKERS)])
        for index, group in enumerate(groups)
    }

    handles = []
    for panel_index, facet in enumerate(facets):
        ax = axes.flat[panel_index]
        ax.set_facecolor("#FBFAF7")
        draw_triangle(ax, labels)
        panel_rows = [row for row in rows if row.facet == facet]
        for group in groups:
            subset = [row for row in panel_rows if row.group == group]
            if not subset:
                continue
            color, marker = style[group]
            points = [ternary_xy(row) for row in subset]
            artist = ax.scatter(
                [point[0] for point in points],
                [point[1] for point in points],
                s=35,
                c=color,
                marker=marker,
                edgecolors="#FBFAF7",
                linewidths=0.75,
                alpha=0.86,
                zorder=4,
                label=group,
            )
            if panel_index == 0:
                handles.append(artist)
            for row, (x, y) in zip(subset, points):
                if row.label:
                    ax.annotate(
                        row.label,
                        (x, y),
                        xytext=(4, 4),
                        textcoords="offset points",
                        fontsize=7.2,
                        color="#202528",
                    )
        ax.set_title(f"{facet} · n={len(panel_rows)}", loc="left", fontsize=10.2, fontweight="bold", pad=7)

    for ax in axes.flat[len(facets):]:
        ax.remove()
    subtitle = f"{len(rows)} samples · {len(groups)} group(s) · {len(facets)} facet(s)"
    if args.normalize:
        subtitle += " · rows explicitly normalized for display"
    fig.suptitle(args.title, x=0.055, y=0.985, ha="left", fontsize=15.2, fontweight="bold", color="#182128")
    fig.text(0.055, 0.945, provenance_note or subtitle, ha="left", va="top", fontsize=8.8, color="#59666F")
    if provenance_note:
        fig.text(0.055, 0.918, subtitle, ha="left", va="top", fontsize=8.4, color="#59666F")
    if len(groups) > 1:
        fig.legend(handles, groups, loc="lower center", bbox_to_anchor=(0.5, 0.018), ncol=min(5, len(groups)), frameon=False, fontsize=8.5)
    fig.text(
        0.055,
        0.022,
        "Compositional display only; grid lines are not thresholds or significance regions.",
        ha="left",
        va="bottom",
        fontsize=7.6,
        color="#66737B",
    )
    top = 0.875 if provenance_note else 0.90
    bottom = 0.10 if len(groups) > 1 else 0.075
    fig.subplots_adjust(left=0.045, right=0.975, top=top, bottom=bottom, wspace=0.20, hspace=0.30)

    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
    png_path = args.output_prefix.with_suffix(".png")
    svg_path = args.output_prefix.with_suffix(".svg")
    fig.savefig(png_path, dpi=args.dpi, facecolor=fig.get_facecolor())
    fig.savefig(svg_path, facecolor=fig.get_facecolor())
    plt.close(fig)
    mode = "explicitly normalized" if args.normalize else f"validated sum target {args.sum_target:g}"
    print(f"Validated {len(rows)} rows, {len(groups)} group(s), {len(facets)} facet(s); {mode}; excluded rows: 0.")
    if provenance_note:
        print(provenance_note)
    print(f"Wrote {png_path}")
    print(f"Wrote {svg_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
