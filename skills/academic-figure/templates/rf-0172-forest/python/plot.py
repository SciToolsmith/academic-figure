#!/usr/bin/env python3
"""Render validated, panel-aware forest plots from a single long-form CSV."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import ticker
from matplotlib.lines import Line2D


SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SCRIPT_DIR.parent
DEFAULT_INPUT = TEMPLATE_DIR / "demo" / "demo_simulated_seed172.csv"
DEFAULT_OUTPUT_PREFIX = TEMPLATE_DIR / "output" / "forest_python"

REQUIRED_COLUMNS = ("label", "estimate", "ci_low", "ci_high")
ADDITIVE_METRICS = {
    "",
    "additive",
    "difference",
    "mean_difference",
    "risk_difference",
    "beta",
    "coefficient",
    "correlation",
    "log_ratio",
    "log_odds",
    "log_hazard",
}
RATIO_METRICS = {
    "ratio",
    "odds_ratio",
    "risk_ratio",
    "rate_ratio",
    "hazard_ratio",
    "prevalence_ratio",
}
BASE_COLORS = (
    "#277DA1",
    "#D97745",
    "#548C68",
    "#7A6FA6",
    "#B34F62",
    "#4D646F",
    "#C39A2E",
    "#4C956C",
)
MARKERS = ("o", "s", "D", "^", "v", "P", "X", "h")
BACKGROUND = "#FBFAF7"
INK = "#17242C"
MUTED = "#5C696E"
GRID = "#DADDD8"


@dataclass(frozen=True)
class EstimateRow:
    source_row: int
    label: str
    estimate: float
    ci_low: float
    ci_high: float
    panel: str
    section: str
    series: str
    metric: str
    family: str
    null_value: float
    p_value: Optional[float]
    n: Optional[int]


@dataclass(frozen=True)
class PanelLayout:
    name: str
    rows: Tuple[EstimateRow, ...]
    items: Tuple[Tuple[str, str, str], ...]
    label_y: Dict[Tuple[str, str], int]
    series: Tuple[str, ...]
    family: str
    null_value: float


def ordered_unique(values: Iterable[str]) -> List[str]:
    return list(OrderedDict.fromkeys(values))


def normalize_metric(value: str) -> Tuple[str, str]:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in ADDITIVE_METRICS:
        return normalized or "additive", "additive"
    if normalized in RATIO_METRICS:
        return normalized, "ratio"
    allowed = sorted((ADDITIVE_METRICS | RATIO_METRICS) - {""})
    raise ValueError(
        f"Unsupported metric {value!r}. Use one of: {', '.join(allowed)}"
    )


def required_float(row: dict, name: str, row_number: int) -> float:
    raw = str(row.get(name, "")).strip()
    if not raw:
        raise ValueError(f"Row {row_number}: {name} is required")
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(f"Row {row_number}: {name} must be numeric") from error
    if not math.isfinite(value):
        raise ValueError(f"Row {row_number}: {name} must be finite")
    return value


def optional_float(row: dict, name: str, row_number: int) -> Optional[float]:
    raw = str(row.get(name, "")).strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(f"Row {row_number}: {name} must be numeric when supplied") from error
    if not math.isfinite(value):
        raise ValueError(f"Row {row_number}: {name} must be finite when supplied")
    return value


def read_and_validate(path: Path) -> Tuple[List[EstimateRow], str]:
    if not path.is_file():
        raise FileNotFoundError(f"Input CSV not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = [name for name in REQUIRED_COLUMNS if name not in fieldnames]
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(missing)}")
        raw_rows = list(reader)

    if not raw_rows:
        raise ValueError("Input CSV contains no estimate rows")

    rows: List[EstimateRow] = []
    identities = set()
    statuses: List[str] = []
    seeds: List[str] = []

    for row_number, raw_row in enumerate(raw_rows, start=2):
        label = str(raw_row.get("label", "")).strip()
        if not label:
            raise ValueError(f"Row {row_number}: label must not be blank")

        estimate = required_float(raw_row, "estimate", row_number)
        ci_low = required_float(raw_row, "ci_low", row_number)
        ci_high = required_float(raw_row, "ci_high", row_number)
        if not ci_low < ci_high:
            raise ValueError(f"Row {row_number}: require ci_low < ci_high")
        if not ci_low <= estimate <= ci_high:
            raise ValueError(
                f"Row {row_number}: estimate must lie within [ci_low, ci_high]"
            )

        panel = str(raw_row.get("panel", "")).strip() or "Forest plot"
        section = str(raw_row.get("section", "")).strip()
        series = str(raw_row.get("series", "")).strip() or "Estimate"
        metric, family = normalize_metric(str(raw_row.get("metric", "")))

        supplied_null = optional_float(raw_row, "null_value", row_number)
        null_value = (
            supplied_null
            if supplied_null is not None
            else (1.0 if family == "ratio" else 0.0)
        )
        if family == "ratio":
            if not math.isclose(null_value, 1.0, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError(
                    f"Row {row_number}: ratio metrics require null_value = 1"
                )
            if min(estimate, ci_low, ci_high) <= 0:
                raise ValueError(
                    f"Row {row_number}: ratio estimates and CI bounds must be > 0"
                )

        p_value = optional_float(raw_row, "p_value", row_number)
        if p_value is not None and not 0.0 <= p_value <= 1.0:
            raise ValueError(f"Row {row_number}: p_value must lie within [0, 1]")

        supplied_n = optional_float(raw_row, "n", row_number)
        n_value: Optional[int] = None
        if supplied_n is not None:
            if supplied_n <= 0 or not math.isclose(
                supplied_n, round(supplied_n), rel_tol=0.0, abs_tol=1e-9
            ):
                raise ValueError(f"Row {row_number}: n must be a positive integer")
            n_value = int(round(supplied_n))

        identity = (panel, section, label, series)
        if identity in identities:
            raise ValueError(
                "Duplicate panel/section/label/series combination at "
                f"row {row_number}: {identity}"
            )
        identities.add(identity)

        status = str(raw_row.get("data_status", "")).strip()
        seed = str(raw_row.get("simulation_seed", "")).strip()
        if status:
            statuses.append(status)
        if seed:
            seeds.append(seed)

        rows.append(
            EstimateRow(
                source_row=row_number,
                label=label,
                estimate=estimate,
                ci_low=ci_low,
                ci_high=ci_high,
                panel=panel,
                section=section,
                series=series,
                metric=metric,
                family=family,
                null_value=null_value,
                p_value=p_value,
                n=n_value,
            )
        )

    for panel in ordered_unique(row.panel for row in rows):
        panel_rows = [row for row in rows if row.panel == panel]
        families = {row.family for row in panel_rows}
        if len(families) != 1:
            raise ValueError(
                f"Panel {panel!r} mixes additive and ratio metrics; split it into panels"
            )
        reference = panel_rows[0].null_value
        if any(
            not math.isclose(row.null_value, reference, rel_tol=0.0, abs_tol=1e-12)
            for row in panel_rows[1:]
        ):
            raise ValueError(f"Panel {panel!r} contains inconsistent null_value entries")

    unique_statuses = ordered_unique(statuses)
    unique_seeds = ordered_unique(seeds)
    if len(unique_statuses) > 1:
        raise ValueError("data_status must be constant when supplied")
    if len(unique_seeds) > 1:
        raise ValueError("simulation_seed must be constant when supplied")

    if unique_statuses and unique_statuses[0].upper() == "SIMULATED":
        if not unique_seeds:
            raise ValueError("SIMULATED data must supply simulation_seed")
        data_note = f"SIMULATED DEMONSTRATION DATA · fixed seed {unique_seeds[0]}"
    else:
        data_note = "SOURCE-SUPPLIED ESTIMATES"

    return rows, data_note


def build_layouts(rows: Sequence[EstimateRow]) -> List[PanelLayout]:
    layouts: List[PanelLayout] = []
    for panel_name in ordered_unique(row.panel for row in rows):
        panel_rows = tuple(row for row in rows if row.panel == panel_name)
        sections = ordered_unique(row.section for row in panel_rows)
        items: List[Tuple[str, str, str]] = []
        label_y: Dict[Tuple[str, str], int] = {}
        for section in sections:
            if section:
                items.append(("header", section, ""))
            labels = ordered_unique(
                row.label for row in panel_rows if row.section == section
            )
            for label in labels:
                label_y[(section, label)] = len(items)
                items.append(("label", label, section))

        layouts.append(
            PanelLayout(
                name=panel_name,
                rows=panel_rows,
                items=tuple(items),
                label_y=label_y,
                series=tuple(ordered_unique(row.series for row in panel_rows)),
                family=panel_rows[0].family,
                null_value=panel_rows[0].null_value,
            )
        )
    return layouts


def style_map(series_order: Sequence[str]) -> Dict[str, Tuple[str, str]]:
    return {
        series: (BASE_COLORS[index % len(BASE_COLORS)], MARKERS[index % len(MARKERS)])
        for index, series in enumerate(series_order)
    }


def series_offsets(series_order: Sequence[str]) -> Dict[str, float]:
    count = len(series_order)
    if count == 1:
        return {series_order[0]: 0.0}
    span = min(0.60, 0.30 * (count - 1))
    return {
        series: -span / 2 + span * index / (count - 1)
        for index, series in enumerate(series_order)
    }


def x_limits(layout: PanelLayout) -> Tuple[float, float]:
    values = [layout.null_value]
    for row in layout.rows:
        values.extend((row.ci_low, row.ci_high))
    lower = min(values)
    upper = max(values)
    if layout.family == "ratio":
        log_lower = math.log(lower)
        log_upper = math.log(upper)
        padding = max((log_upper - log_lower) * 0.09, 0.06)
        return math.exp(log_lower - padding), math.exp(log_upper + padding)
    span = upper - lower
    padding = max(span * 0.09, 0.05)
    return lower - padding, upper + padding


def format_number(value: float) -> str:
    magnitude = abs(value)
    if magnitude and (magnitude < 0.01 or magnitude >= 1000):
        return f"{value:.2e}"
    return f"{value:.2f}"


def format_p(value: float) -> str:
    return f"{value:.2e}" if value < 0.001 else f"{value:.3f}"


def summary_label(row: EstimateRow) -> str:
    pieces = [
        f"{format_number(row.estimate)} "
        f"[{format_number(row.ci_low)}, {format_number(row.ci_high)}]"
    ]
    if row.p_value is not None:
        pieces.append(f"p={format_p(row.p_value)}")
    if row.n is not None:
        pieces.append(f"n={row.n:,}")
    return " · ".join(pieces)


def axis_label(layout: PanelLayout) -> str:
    if layout.family == "ratio":
        return "Ratio effect (95% CI; logarithmic axis)"
    return "Additive effect (95% CI; linear axis)"


def render(
    rows: Sequence[EstimateRow],
    data_note: str,
    title: str,
    output_prefix: Path,
    dpi: int,
) -> Tuple[Path, Path]:
    layouts = build_layouts(rows)
    global_series = ordered_unique(row.series for row in rows)
    styles = style_map(global_series)
    max_label_length = max(len(row.label) for row in rows)
    figure_width = min(17.0, max(10.8, 10.8 + 0.055 * (max_label_length - 24)))
    item_counts = [len(layout.items) for layout in layouts]
    figure_height = max(
        5.4,
        1.7 + sum(max(2.6, count * 0.43 + 1.0) for count in item_counts),
    )

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.0,
            "axes.edgecolor": "#6D7A80",
            "axes.labelcolor": INK,
            "xtick.color": "#3E4C53",
            "ytick.color": INK,
            "text.color": INK,
            "axes.unicode_minus": False,
            "svg.fonttype": "none",
        }
    )

    figure = plt.figure(figsize=(figure_width, figure_height), facecolor=BACKGROUND)
    grid = figure.add_gridspec(
        len(layouts),
        1,
        height_ratios=[max(2.6, count * 0.43 + 1.0) for count in item_counts],
        hspace=0.72,
    )
    figure.subplots_adjust(left=0.29, right=0.70, top=0.88, bottom=0.09)

    figure.text(
        0.035,
        0.975,
        title,
        ha="left",
        va="top",
        fontsize=18,
        fontweight="bold",
    )
    figure.text(
        0.035,
        0.943,
        f"{data_note} · estimates and intervals are plotted as supplied; no statistics are recomputed",
        ha="left",
        va="top",
        fontsize=9.2,
        color=MUTED,
    )

    for panel_index, layout in enumerate(layouts):
        axis = figure.add_subplot(grid[panel_index, 0])
        axis.set_facecolor(BACKGROUND)
        lower, upper = x_limits(layout)
        axis.set_xlim(lower, upper)
        axis.set_ylim(-0.65, len(layout.items) - 0.35)
        axis.invert_yaxis()
        if layout.family == "ratio":
            axis.set_xscale("log")
            axis.xaxis.set_major_locator(ticker.LogLocator(base=10, subs=(1.0, 2.0, 5.0)))
            axis.xaxis.set_major_formatter(ticker.FuncFormatter(lambda value, _: f"{value:g}"))
            axis.xaxis.set_minor_formatter(ticker.NullFormatter())
        else:
            axis.xaxis.set_major_locator(ticker.MaxNLocator(nbins=6))

        axis.grid(axis="x", color=GRID, linewidth=0.65, zorder=0)
        axis.axvline(
            layout.null_value,
            color="#5F6D73",
            linestyle=(0, (4, 3)),
            linewidth=1.0,
            zorder=1,
        )
        axis.spines[["top", "right", "left"]].set_visible(False)
        axis.spines["bottom"].set_color("#738087")
        axis.tick_params(axis="y", length=0, pad=8)
        axis.tick_params(axis="x", labelsize=8.5)
        axis.set_xlabel(axis_label(layout), labelpad=8)
        axis.set_title(layout.name, loc="left", fontsize=12.5, fontweight="bold", pad=17)

        tick_positions: List[int] = []
        tick_labels: List[str] = []
        for index, (kind, text, _section) in enumerate(layout.items):
            if kind == "label":
                tick_positions.append(index)
                tick_labels.append(text)
            else:
                axis.axhline(index, color="#BFC5C2", linewidth=0.75, zorder=0)
                axis.text(
                    0.01,
                    index,
                    text,
                    transform=axis.get_yaxis_transform(),
                    ha="left",
                    va="center",
                    fontsize=8.2,
                    fontweight="bold",
                    color="#415159",
                    bbox={"facecolor": BACKGROUND, "edgecolor": "none", "pad": 1.5},
                )
        axis.set_yticks(tick_positions)
        axis.set_yticklabels(tick_labels, fontsize=8.5)

        offsets = series_offsets(layout.series)
        for row in layout.rows:
            color, marker = styles[row.series]
            y_value = layout.label_y[(row.section, row.label)] + offsets[row.series]
            axis.plot(
                [row.ci_low, row.ci_high],
                [y_value, y_value],
                color=color,
                linewidth=1.45,
                alpha=0.9,
                zorder=2,
            )
            axis.vlines(
                [row.ci_low, row.ci_high],
                y_value - 0.045,
                y_value + 0.045,
                color=color,
                linewidth=0.9,
                alpha=0.9,
                zorder=2,
            )
            axis.scatter(
                row.estimate,
                y_value,
                s=38,
                marker=marker,
                facecolor=color,
                edgecolor="white",
                linewidth=0.7,
                zorder=3,
            )
            axis.text(
                1.025,
                y_value,
                summary_label(row),
                transform=axis.get_yaxis_transform(),
                ha="left",
                va="center",
                fontsize=7.5,
                color="#46545B",
                clip_on=False,
            )

        axis.text(
            1.025,
            1.035,
            "Estimate [95% CI] · optional p and n",
            transform=axis.transAxes,
            ha="left",
            va="bottom",
            fontsize=7.8,
            fontweight="bold",
            color="#526068",
            clip_on=False,
        )

        if len(layout.series) > 1:
            handles = [
                Line2D(
                    [0],
                    [0],
                    marker=styles[series][1],
                    linestyle="none",
                    markerfacecolor=styles[series][0],
                    markeredgecolor="white",
                    markersize=6.5,
                    label=series,
                )
                for series in layout.series
            ]
            axis.legend(
                handles=handles,
                loc="upper right",
                bbox_to_anchor=(1.0, 1.17),
                ncol=min(4, len(handles)),
                frameon=False,
                fontsize=7.8,
                handletextpad=0.35,
                columnspacing=0.9,
                borderaxespad=0,
            )

    figure.text(
        0.035,
        0.025,
        "Additive panels use linear axes; ratio panels require positive estimates and bounds, null = 1, and logarithmic axes.",
        ha="left",
        va="bottom",
        fontsize=8.0,
        color=MUTED,
    )

    prefix = output_prefix.with_suffix("") if output_prefix.suffix else output_prefix
    prefix.parent.mkdir(parents=True, exist_ok=True)
    png_path = prefix.with_suffix(".png")
    svg_path = prefix.with_suffix(".svg")
    figure.savefig(png_path, dpi=dpi, bbox_inches="tight", facecolor=BACKGROUND)
    figure.savefig(svg_path, bbox_inches="tight", facecolor=BACKGROUND)
    plt.close(figure)
    return png_path, svg_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render additive and ratio forest plots from a validated long-form CSV."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT_PREFIX)
    parser.add_argument(
        "--title", default="Forest plot of source-supplied effect estimates"
    )
    parser.add_argument("--dpi", type=int, default=320)
    args = parser.parse_args()
    if args.dpi < 150:
        parser.error("--dpi must be at least 150")
    return args


def main() -> int:
    args = parse_args()
    try:
        rows, data_note = read_and_validate(args.input)
        png_path, svg_path = render(
            rows=rows,
            data_note=data_note,
            title=args.title,
            output_prefix=args.output_prefix,
            dpi=args.dpi,
        )
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    panel_summary = ", ".join(
        f"{panel}={sum(row.panel == panel for row in rows)} rows"
        for panel in ordered_unique(row.panel for row in rows)
    )
    print(f"Validated {len(rows)} estimate rows ({panel_summary})")
    print(f"Data status: {data_note}")
    print(f"PNG: {png_path}")
    print(f"SVG: {svg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
