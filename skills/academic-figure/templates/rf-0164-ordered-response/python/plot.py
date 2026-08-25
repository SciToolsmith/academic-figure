#!/usr/bin/env python3
"""Render validated ordered-response curves from a long-form CSV."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
from matplotlib import ticker
from matplotlib.lines import Line2D


SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SCRIPT_DIR.parent
DEFAULT_INPUT = TEMPLATE_DIR / "demo" / "demo_simulated_seed164.csv"
DEFAULT_OUTPUT_PREFIX = Path.cwd() / "ordered_response_python"

BACKGROUND = "#FBFAF7"
INK = "#20282C"
MUTED = "#627078"
GRID = "#E5E2DC"
COLORS = (
    "#287D9B",
    "#D96B35",
    "#4F8A5B",
    "#8D65A8",
    "#B68A1F",
    "#5875B5",
    "#B64E68",
    "#477E79",
)
LINESTYLES = ("-", "--", "-.", ":")
MARKERS = ("o", "s", "^", "D", "v", "P", "X", "<", ">")
REQUIRED_COLUMNS = ("series", "group", "x", "y", "data_mode")


class ContractError(ValueError):
    """Raised when the CSV violates the plotting contract."""


@dataclass(frozen=True)
class ResponseRow:
    source_line: int
    series: str
    group: str
    x: float
    y: float
    data_mode: str
    replicate: str
    panel: str
    y_lower: Optional[float]
    y_upper: Optional[float]
    x_scale: str
    data_status: str
    simulation_seed: str


@dataclass(frozen=True)
class PanelSpec:
    name: str
    rows: Tuple[ResponseRow, ...]
    data_mode: str
    x_scale: str
    curves: Tuple[Tuple[str, str], ...]


def ordered_unique(values: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def ordered_unique_pairs(values: Iterable[Tuple[str, str]]) -> List[Tuple[str, str]]:
    seen = set()
    result: List[Tuple[str, str]] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def parse_number(value: str, field: str, line: int) -> float:
    text = value.strip()
    if not text:
        raise ContractError(f"Line {line}: '{field}' must not be blank.")
    try:
        number = float(text)
    except ValueError as exc:
        raise ContractError(
            f"Line {line}: '{field}' must be numeric, got {text!r}."
        ) from exc
    if not math.isfinite(number):
        raise ContractError(f"Line {line}: '{field}' must be finite.")
    return number


def parse_optional_number(value: str, field: str, line: int) -> Optional[float]:
    if not value.strip():
        return None
    return parse_number(value, field, line)


def read_and_validate(path: Path) -> Tuple[List[ResponseRow], str]:
    if not path.is_file():
        raise ContractError(f"Input CSV does not exist: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ContractError("Input CSV has no header row.")
        headers = [header.strip() for header in reader.fieldnames]
        if any(not header for header in headers):
            raise ContractError("CSV headers must not be blank.")
        if len(headers) != len(set(headers)):
            raise ContractError("CSV headers must be unique.")
        missing = [column for column in REQUIRED_COLUMNS if column not in headers]
        if missing:
            raise ContractError(f"Missing required columns: {', '.join(missing)}")

        rows: List[ResponseRow] = []
        for line, raw in enumerate(reader, start=2):
            if raw is None or all(not str(value or "").strip() for value in raw.values()):
                continue

            def text(column: str) -> str:
                return str(raw.get(column, "") or "").strip()

            series = text("series")
            group = text("group")
            if not series:
                raise ContractError(f"Line {line}: 'series' must not be blank.")
            if not group:
                raise ContractError(f"Line {line}: 'group' must not be blank.")

            data_mode = text("data_mode").lower()
            if data_mode not in {"raw", "summary"}:
                raise ContractError(
                    f"Line {line}: 'data_mode' must be 'raw' or 'summary'."
                )
            x_scale = text("x_scale").lower() or "linear"
            if x_scale not in {"linear", "log"}:
                raise ContractError(
                    f"Line {line}: 'x_scale' must be 'linear' or 'log'."
                )

            x_value = parse_number(text("x"), "x", line)
            y_value = parse_number(text("y"), "y", line)
            y_lower = parse_optional_number(text("y_lower"), "y_lower", line)
            y_upper = parse_optional_number(text("y_upper"), "y_upper", line)
            if (y_lower is None) != (y_upper is None):
                raise ContractError(
                    f"Line {line}: provide both 'y_lower' and 'y_upper', or neither."
                )
            if y_lower is not None and not (y_lower < y_upper):
                raise ContractError(f"Line {line}: require y_lower < y_upper.")
            if y_lower is not None and not (y_lower <= y_value <= y_upper):
                raise ContractError(
                    f"Line {line}: y must lie inside [y_lower, y_upper]."
                )

            replicate = text("replicate")
            if data_mode == "raw" and y_lower is not None:
                raise ContractError(
                    f"Line {line}: raw rows cannot supply precomputed intervals."
                )
            if data_mode == "summary" and replicate:
                raise ContractError(
                    f"Line {line}: summary rows cannot carry a replicate identifier."
                )
            if x_scale == "log" and x_value <= 0:
                raise ContractError(
                    f"Line {line}: logarithmic x requires x > 0."
                )

            rows.append(
                ResponseRow(
                    source_line=line,
                    series=series,
                    group=group,
                    x=x_value,
                    y=y_value,
                    data_mode=data_mode,
                    replicate=replicate,
                    panel=text("panel") or "Ordered response",
                    y_lower=y_lower,
                    y_upper=y_upper,
                    x_scale=x_scale,
                    data_status=text("data_status").upper(),
                    simulation_seed=text("simulation_seed"),
                )
            )

    if not rows:
        raise ContractError("Input CSV contains no data rows.")

    data_note = validate_metadata(rows)
    validate_panel_contracts(rows)
    return rows, data_note


def validate_metadata(rows: Sequence[ResponseRow]) -> str:
    statuses = ordered_unique(row.data_status for row in rows if row.data_status)
    seeds = ordered_unique(row.simulation_seed for row in rows if row.simulation_seed)
    if len(statuses) > 1:
        raise ContractError("'data_status' must be constant across the file.")
    if len(seeds) > 1:
        raise ContractError("'simulation_seed' must be constant across the file.")

    if statuses == ["SIMULATED"]:
        if any(row.data_status != "SIMULATED" for row in rows):
            raise ContractError("Every simulated row must declare data_status=SIMULATED.")
        if len(seeds) != 1 or any(not row.simulation_seed for row in rows):
            raise ContractError(
                "Simulated data must provide one fixed simulation_seed on every row."
            )
        try:
            seed_number = int(seeds[0])
        except ValueError as exc:
            raise ContractError("simulation_seed must be a positive integer.") from exc
        if seed_number <= 0 or str(seed_number) != seeds[0]:
            raise ContractError("simulation_seed must be a positive integer.")
        return f"SIMULATED DEMONSTRATION DATA · fixed seed {seed_number}"

    if seeds:
        raise ContractError(
            "simulation_seed is only valid when data_status is SIMULATED."
        )
    return "SOURCE-SUPPLIED DATA"


def validate_panel_contracts(rows: Sequence[ResponseRow]) -> None:
    panels = ordered_unique(row.panel for row in rows)
    for panel in panels:
        panel_rows = [row for row in rows if row.panel == panel]
        modes = {row.data_mode for row in panel_rows}
        scales = {row.x_scale for row in panel_rows}
        if len(modes) != 1:
            raise ContractError(
                f"Panel {panel!r} mixes raw and summary rows; split them into panels."
            )
        if len(scales) != 1:
            raise ContractError(
                f"Panel {panel!r} mixes linear and log x scales."
            )

        curves = ordered_unique_pairs((row.group, row.series) for row in panel_rows)
        for group, series in curves:
            curve_rows = [
                row
                for row in panel_rows
                if row.group == group and row.series == series
            ]
            unique_x = sorted({row.x for row in curve_rows})
            if len(unique_x) < 2:
                raise ContractError(
                    f"Panel {panel!r}, group {group!r}, series {series!r} "
                    "needs at least two distinct numeric x values."
                )

            by_x: Dict[float, List[ResponseRow]] = defaultdict(list)
            for row in curve_rows:
                by_x[row.x].append(row)
            for x_value, cluster in by_x.items():
                if panel_rows[0].data_mode == "summary" and len(cluster) > 1:
                    lines = ", ".join(str(row.source_line) for row in cluster)
                    raise ContractError(
                        f"Summary rows must be unique by panel/group/series/x; "
                        f"duplicate x={x_value:g} at lines {lines}."
                    )
                if panel_rows[0].data_mode == "raw" and len(cluster) > 1:
                    if any(not row.replicate for row in cluster):
                        raise ContractError(
                            f"Repeated raw observations at x={x_value:g} in panel "
                            f"{panel!r}, group {group!r}, series {series!r} require "
                            "nonblank replicate identifiers."
                        )
                    replicate_ids = [row.replicate for row in cluster]
                    if len(replicate_ids) != len(set(replicate_ids)):
                        raise ContractError(
                            f"Raw replicate identifiers must be unique within each "
                            f"panel/group/series/x cluster (x={x_value:g})."
                        )


def build_panels(rows: Sequence[ResponseRow]) -> List[PanelSpec]:
    panels: List[PanelSpec] = []
    for panel_name in ordered_unique(row.panel for row in rows):
        panel_rows = tuple(row for row in rows if row.panel == panel_name)
        panels.append(
            PanelSpec(
                name=panel_name,
                rows=panel_rows,
                data_mode=panel_rows[0].data_mode,
                x_scale=panel_rows[0].x_scale,
                curves=tuple(
                    ordered_unique_pairs(
                        (row.group, row.series) for row in panel_rows
                    )
                ),
            )
        )
    return panels


def axis_limits(values: Sequence[float], logarithmic: bool = False) -> Tuple[float, float]:
    lower, upper = min(values), max(values)
    if logarithmic:
        log_lower, log_upper = math.log(lower), math.log(upper)
        span = log_upper - log_lower
        padding = max(0.07 * span, 0.08)
        return math.exp(log_lower - padding), math.exp(log_upper + padding)
    span = upper - lower
    padding = max(0.07 * span, 0.04 * max(abs(lower), abs(upper), 1.0))
    return lower - padding, upper + padding


def curve_label(
    group: str,
    series: str,
    panel_groups: Sequence[str],
    panel_series: Sequence[str],
) -> str:
    if len(panel_groups) > 1 and len(panel_series) > 1:
        return f"{group} · {series}"
    if len(panel_groups) > 1:
        return group
    if len(panel_series) > 1:
        return series
    return f"{group} · {series}" if group != series else group


def render(
    rows: Sequence[ResponseRow],
    data_note: str,
    output_prefix: Path,
    title: str,
    x_label: str,
    y_label: str,
    dpi: int,
) -> Tuple[Path, Path]:
    panels = build_panels(rows)
    groups = ordered_unique(row.group for row in rows)
    series_values = ordered_unique(row.series for row in rows)
    group_colors = {
        group: COLORS[index % len(COLORS)] for index, group in enumerate(groups)
    }
    series_styles = {
        series: (
            LINESTYLES[index % len(LINESTYLES)],
            MARKERS[index % len(MARKERS)],
        )
        for index, series in enumerate(series_values)
    }

    panel_count = len(panels)
    longest_panel = max(len(panel.name) for panel in panels)
    columns = 1 if panel_count == 1 or longest_panel > 34 else min(2, panel_count)
    grid_rows = math.ceil(panel_count / columns)
    longest_curve = max(
        len(f"{group} · {series}")
        for panel in panels
        for group, series in panel.curves
    )
    cell_width = min(8.4, max(6.1, 6.1 + 0.035 * (longest_curve - 20)))
    figure_width = columns * cell_width
    figure_height = 1.45 + grid_rows * 4.15

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.0,
            "axes.edgecolor": "#6D7A80",
            "axes.labelcolor": INK,
            "xtick.color": "#425159",
            "ytick.color": "#425159",
            "text.color": INK,
            "axes.unicode_minus": False,
            "svg.fonttype": "none",
        }
    )

    figure, axes = plt.subplots(
        grid_rows,
        columns,
        figsize=(figure_width, figure_height),
        squeeze=False,
        facecolor=BACKGROUND,
    )
    figure.subplots_adjust(
        left=0.10,
        right=0.97,
        top=0.84,
        bottom=0.12,
        hspace=0.42,
        wspace=0.28,
    )
    figure.text(0.045, 0.975, title, ha="left", va="top", fontsize=18, fontweight="bold")
    figure.text(0.045, 0.935, data_note, ha="left", va="top", fontsize=9.2, color=MUTED)

    for panel_index, panel in enumerate(panels):
        axis = axes[panel_index // columns][panel_index % columns]
        axis.set_facecolor(BACKGROUND)
        axis.set_title(panel.name, loc="left", fontsize=12.0, fontweight="bold", pad=18)
        panel_note = (
            "RAW: points are observations; lines connect arithmetic means at supplied x"
            if panel.data_mode == "raw"
            else "SUMMARY: points and intervals are plotted exactly as supplied"
        )
        axis.text(
            0.0,
            1.02,
            panel_note,
            transform=axis.transAxes,
            ha="left",
            va="bottom",
            fontsize=7.4,
            color=MUTED,
        )
        for spine in ("top", "right"):
            axis.spines[spine].set_visible(False)
        axis.grid(color=GRID, linewidth=0.65, zorder=0)
        axis.set_axisbelow(True)
        axis.set_xlabel(x_label)
        axis.set_ylabel(y_label)

        x_values = [row.x for row in panel.rows]
        y_values = [row.y for row in panel.rows]
        y_values.extend(
            bound
            for row in panel.rows
            for bound in (row.y_lower, row.y_upper)
            if bound is not None
        )
        axis.set_xlim(*axis_limits(x_values, logarithmic=panel.x_scale == "log"))
        axis.set_ylim(*axis_limits(y_values))
        if panel.x_scale == "log":
            axis.set_xscale("log")
            axis.xaxis.set_major_locator(
                ticker.LogLocator(base=10, subs=(1.0, 2.0, 5.0))
            )
            axis.xaxis.set_major_formatter(
                ticker.FuncFormatter(lambda value, _: f"{value:g}")
            )
            axis.xaxis.set_minor_formatter(ticker.NullFormatter())

        panel_groups = ordered_unique(row.group for row in panel.rows)
        panel_series = ordered_unique(row.series for row in panel.rows)
        handles: List[Line2D] = []
        for group, series in panel.curves:
            curve_rows = [
                row
                for row in panel.rows
                if row.group == group and row.series == series
            ]
            color = group_colors[group]
            linestyle, marker = series_styles[series]
            label = curve_label(group, series, panel_groups, panel_series)

            if panel.data_mode == "raw":
                axis.scatter(
                    [row.x for row in curve_rows],
                    [row.y for row in curve_rows],
                    s=18,
                    marker=marker,
                    facecolor=color,
                    edgecolor="white",
                    linewidth=0.35,
                    alpha=0.42,
                    zorder=2,
                )
                by_x: Dict[float, List[float]] = defaultdict(list)
                for row in curve_rows:
                    by_x[row.x].append(row.y)
                ordered_x = sorted(by_x)
                ordered_y = [statistics.fmean(by_x[x_value]) for x_value in ordered_x]
            else:
                sorted_rows = sorted(curve_rows, key=lambda row: row.x)
                ordered_x = [row.x for row in sorted_rows]
                ordered_y = [row.y for row in sorted_rows]
                interval_rows = [row for row in sorted_rows if row.y_lower is not None]
                if interval_rows:
                    axis.errorbar(
                        [row.x for row in interval_rows],
                        [row.y for row in interval_rows],
                        yerr=[
                            [row.y - row.y_lower for row in interval_rows],
                            [row.y_upper - row.y for row in interval_rows],
                        ],
                        fmt="none",
                        ecolor=color,
                        elinewidth=1.0,
                        capsize=2.6,
                        alpha=0.72,
                        zorder=2,
                    )

            axis.plot(
                ordered_x,
                ordered_y,
                color=color,
                linestyle=linestyle,
                linewidth=1.65,
                marker=marker,
                markersize=4.7,
                markerfacecolor=color,
                markeredgecolor="white",
                markeredgewidth=0.55,
                zorder=3,
            )
            handles.append(
                Line2D(
                    [0],
                    [0],
                    color=color,
                    linestyle=linestyle,
                    linewidth=1.5,
                    marker=marker,
                    markerfacecolor=color,
                    markeredgecolor="white",
                    markersize=5.0,
                    label=label,
                )
            )

        curve_count = len(handles)
        axis.legend(
            handles=handles,
            loc="best",
            frameon=True,
            facecolor=BACKGROUND,
            edgecolor="#D7D5CF",
            framealpha=0.92,
            fontsize=max(6.6, 8.0 - 0.12 * max(0, curve_count - 4)),
            ncol=2 if curve_count > 6 else 1,
            handlelength=2.2,
        )

    for empty_index in range(panel_count, grid_rows * columns):
        axes[empty_index // columns][empty_index % columns].set_visible(False)

    figure.text(
        0.045,
        0.025,
        "Lines follow numerically ordered supplied x positions. No smoothing, unsampled-x interpolation, or peak-based statistical inference is performed.",
        ha="left",
        va="bottom",
        fontsize=7.8,
        color=MUTED,
    )

    prefix = output_prefix.expanduser().with_suffix("")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    png_path = prefix.with_suffix(".png")
    svg_path = prefix.with_suffix(".svg")
    figure.savefig(png_path, dpi=dpi, bbox_inches="tight", facecolor=BACKGROUND)
    figure.savefig(svg_path, bbox_inches="tight", facecolor=BACKGROUND)
    plt.close(figure)
    return png_path, svg_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render raw or pre-summarized ordered-response curves."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT_PREFIX)
    parser.add_argument("--title", default="Ordered response curves")
    parser.add_argument("--x-label", default="Ordered input")
    parser.add_argument("--y-label", default="Response")
    parser.add_argument("--dpi", type=int, default=320)
    args = parser.parse_args()
    if args.dpi < 150:
        parser.error("--dpi must be at least 150.")
    return args


def main() -> int:
    args = parse_args()
    try:
        rows, data_note = read_and_validate(args.input.expanduser())
        png_path, svg_path = render(
            rows=rows,
            data_note=data_note,
            output_prefix=args.output_prefix,
            title=args.title,
            x_label=args.x_label,
            y_label=args.y_label,
            dpi=args.dpi,
        )
    except ContractError as exc:
        raise SystemExit(f"Input validation failed: {exc}") from exc

    panel_counts = []
    for panel in build_panels(rows):
        panel_counts.append(
            f"{panel.name}={len(panel.rows)} {panel.data_mode} rows ({panel.x_scale} x)"
        )
    print(f"Validated {len(rows)} rows: " + "; ".join(panel_counts))
    print(f"Data status: {data_note}")
    print(f"PNG: {png_path.resolve()}")
    print(f"SVG: {svg_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
