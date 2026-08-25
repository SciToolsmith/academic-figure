#!/usr/bin/env python3
"""Render a generalized raincloud plot from a semantic CSV contract."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["svg.fonttype"] = "none"

import matplotlib.pyplot as plt
from matplotlib.colors import to_hex
from matplotlib.patches import Rectangle
import numpy as np


DEFAULT_TITLE = "Group distributions"
DEFAULT_X_LABEL = "Value"
GOLDEN_FRACTION = 0.6180339887498949
MAX_REPORTED_ERRORS = 10


class DataContractError(ValueError):
    """Raised when an input file violates the public data contract."""


@dataclass(frozen=True)
class Observation:
    facet: str
    group: str
    value: float
    observation_id: str
    source_row: int


@dataclass(frozen=True)
class InputData:
    observations: tuple[Observation, ...]
    facet_order: tuple[str, ...]
    group_order: tuple[str, ...]
    has_facet: bool
    has_id: bool


@dataclass(frozen=True)
class DensityProfile:
    density: np.ndarray | None
    bandwidth: float | None
    status: str


def ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def read_input(path: Path) -> InputData:
    if not path.is_file():
        raise DataContractError(f"input file does not exist: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise DataContractError("input must contain a header row")
        fields = list(reader.fieldnames)
        if len(fields) != len(set(fields)):
            raise DataContractError("input contains duplicate column names")

        missing_columns = [name for name in ("group", "value") if name not in fields]
        if missing_columns:
            raise DataContractError(
                "missing required column(s): " + ", ".join(missing_columns)
            )

        has_facet = "facet" in fields
        has_id = "id" in fields
        errors: list[str] = []
        observations: list[Observation] = []

        for row_number, row in enumerate(reader, start=2):
            raw_group = row.get("group")
            raw_value = row.get("value")
            raw_facet = row.get("facet") if has_facet else "All observations"
            raw_id = row.get("id") if has_id else f"row-{row_number}"

            group = "" if raw_group is None else raw_group.strip()
            value_text = "" if raw_value is None else raw_value.strip()
            facet = "" if raw_facet is None else raw_facet.strip()
            observation_id = "" if raw_id is None else raw_id.strip()

            row_errors: list[str] = []
            if not group:
                row_errors.append("group is empty")
            if not value_text:
                row_errors.append("value is empty")
            if not facet:
                row_errors.append("facet is empty")
            if not observation_id:
                row_errors.append("id is empty")

            value = math.nan
            if value_text:
                try:
                    value = float(value_text)
                except ValueError:
                    row_errors.append(f"value is not numeric ({value_text!r})")
                else:
                    if not math.isfinite(value):
                        row_errors.append("value must be finite")

            if row_errors:
                if len(errors) < MAX_REPORTED_ERRORS:
                    errors.append(f"row {row_number}: " + "; ".join(row_errors))
                continue

            observations.append(
                Observation(
                    facet=facet,
                    group=group,
                    value=value,
                    observation_id=observation_id,
                    source_row=row_number,
                )
            )

    if errors:
        suffix = "" if len(errors) < MAX_REPORTED_ERRORS else "\n  (additional errors omitted)"
        raise DataContractError(
            "input rows violate the data contract:\n  - "
            + "\n  - ".join(errors)
            + suffix
        )
    if not observations:
        raise DataContractError("input contains no observations")

    if has_id:
        seen: dict[tuple[str, str, str], int] = {}
        duplicate_messages: list[str] = []
        for item in observations:
            key = (item.facet, item.group, item.observation_id)
            if key in seen:
                if len(duplicate_messages) < MAX_REPORTED_ERRORS:
                    duplicate_messages.append(
                        f"rows {seen[key]} and {item.source_row}: duplicate "
                        f"(facet, group, id)={key!r}"
                    )
            else:
                seen[key] = item.source_row
        if duplicate_messages:
            raise DataContractError(
                "id must be unique within each facet and group:\n  - "
                + "\n  - ".join(duplicate_messages)
            )

    return InputData(
        observations=tuple(observations),
        facet_order=ordered_unique(item.facet for item in observations),
        group_order=ordered_unique(item.group for item in observations),
        has_facet=has_facet,
        has_id=has_id,
    )


def values_for(data: InputData, facet: str, group: str) -> np.ndarray:
    return np.asarray(
        [
            item.value
            for item in data.observations
            if item.facet == facet and item.group == group
        ],
        dtype=float,
    )


def observations_for(
    data: InputData, facet: str, group: str
) -> tuple[Observation, ...]:
    return tuple(
        item
        for item in data.observations
        if item.facet == facet and item.group == group
    )


def density_profile(values: np.ndarray, grid: np.ndarray) -> DensityProfile:
    if values.size < 3:
        return DensityProfile(None, None, "skipped: n < 3")
    if np.unique(values).size < 3:
        return DensityProfile(None, None, "skipped: fewer than 3 distinct values")

    standard_deviation = float(np.std(values, ddof=1))
    scale = max(1.0, float(np.max(np.abs(values))))
    if not math.isfinite(standard_deviation) or standard_deviation <= np.finfo(float).eps * scale:
        return DensityProfile(None, None, "skipped: zero or near-zero variance")

    bandwidth = standard_deviation * values.size ** (-0.2)
    if not math.isfinite(bandwidth) or bandwidth <= np.finfo(float).eps * scale:
        return DensityProfile(None, None, "skipped: invalid bandwidth")

    density = np.zeros_like(grid, dtype=float)
    chunk_size = 2048
    normalizer = values.size * bandwidth * math.sqrt(2.0 * math.pi)
    for start in range(0, values.size, chunk_size):
        chunk = values[start : start + chunk_size]
        with np.errstate(over="ignore", invalid="ignore"):
            z = (grid[:, None] - chunk[None, :]) / bandwidth
            density += np.exp(-0.5 * z * z).sum(axis=1)
    density /= normalizer

    maximum = float(np.max(density))
    if not math.isfinite(maximum) or maximum <= 0:
        return DensityProfile(None, bandwidth, "skipped: density evaluation failed")
    return DensityProfile(density, bandwidth, "drawn")


def box_statistics(values: np.ndarray) -> tuple[float, float, float, float, float]:
    q1, median, q3 = np.quantile(values, (0.25, 0.5, 0.75), method="linear")
    iqr = q3 - q1
    lower_candidates = values[values >= q1 - 1.5 * iqr]
    upper_candidates = values[values <= q3 + 1.5 * iqr]
    lower = float(np.min(lower_candidates)) if lower_candidates.size else float(q1)
    upper = float(np.max(upper_candidates)) if upper_candidates.size else float(q3)
    return lower, float(q1), float(median), float(q3), upper


def global_limits(values: np.ndarray) -> tuple[float, float]:
    lower = float(np.min(values))
    upper = float(np.max(values))
    span = upper - lower
    if span <= 0:
        padding = max(abs(lower) * 0.1, 1.0)
    else:
        overall_sd = float(np.std(values, ddof=1)) if values.size > 1 else 0.0
        padding = max(0.06 * span, 0.25 * overall_sd)
    return lower - padding, upper + padding


def make_group_colors(groups: Sequence[str]) -> dict[str, str]:
    count = len(groups)
    if count <= 10:
        cmap = matplotlib.colormaps["tab10"]
        samples = [cmap(index) for index in range(count)]
    elif count <= 20:
        cmap = matplotlib.colormaps["tab20"]
        samples = [cmap(index) for index in range(count)]
    else:
        cmap = matplotlib.colormaps["hsv"]
        samples = [cmap(index / count) for index in range(count)]
    return {group: to_hex(color) for group, color in zip(groups, samples)}


def figure_geometry(data: InputData) -> tuple[int, int, float, float, int]:
    facet_count = len(data.facet_order)
    if facet_count == 1:
        columns = 1
    elif facet_count <= 4:
        columns = 2
    else:
        columns = min(3, facet_count)
    rows = math.ceil(facet_count / columns)

    groups_per_facet = [
        len(
            ordered_unique(
                item.group for item in data.observations if item.facet == facet
            )
        )
        for facet in data.facet_order
    ]
    maximum_groups = max(groups_per_facet)
    maximum_label_length = max(
        len(f"{group}  n={len(observations_for(data, facet, group))}")
        for facet in data.facet_order
        for group in data.group_order
        if observations_for(data, facet, group)
    )

    panel_width = min(9.6, max(7.2, 6.7 + 0.075 * maximum_label_length))
    panel_height = max(4.2, 1.02 * maximum_groups + 1.7)
    return rows, columns, panel_width * columns, panel_height * rows, maximum_label_length


def report_data(data: InputData, grid: np.ndarray) -> None:
    print(
        f"Loaded {len(data.observations)} rows: {len(data.facet_order)} facet(s), "
        f"{len(data.group_order)} group(s); 0 rows excluded."
    )
    print("facet | group | n | min | median | max | KDE")
    for facet in data.facet_order:
        for group in data.group_order:
            values = values_for(data, facet, group)
            if not values.size:
                continue
            profile = density_profile(values, grid)
            kde_text = profile.status
            if profile.bandwidth is not None and profile.status == "drawn":
                kde_text += f" (bandwidth={profile.bandwidth:.6g})"
            print(
                f"{facet} | {group} | {values.size} | {np.min(values):.6g} | "
                f"{np.median(values):.6g} | {np.max(values):.6g} | {kde_text}"
            )


def draw_figure(data: InputData, title: str, x_label: str) -> plt.Figure:
    all_values = np.asarray([item.value for item in data.observations], dtype=float)
    x_limits = global_limits(all_values)
    grid = np.linspace(x_limits[0], x_limits[1], 512)
    rows, columns, width, height, maximum_label_length = figure_geometry(data)
    colors = make_group_colors(data.group_order)

    figure, axes = plt.subplots(
        rows,
        columns,
        figsize=(width, height),
        squeeze=False,
        sharex=True,
    )
    axes_flat = axes.ravel()

    for panel_index, facet in enumerate(data.facet_order):
        axis = axes_flat[panel_index]
        groups = [
            group
            for group in data.group_order
            if observations_for(data, facet, group)
        ]
        y_positions = np.arange(len(groups) - 1, -1, -1, dtype=float)
        tick_labels: list[str] = []

        for y_base, group in zip(y_positions, groups):
            observations = observations_for(data, facet, group)
            values = np.asarray([item.value for item in observations], dtype=float)
            color = colors[group]
            profile = density_profile(values, grid)

            axis.plot(
                [x_limits[0], x_limits[1]],
                [y_base, y_base],
                color="#D9DEE5",
                linewidth=0.7,
                zorder=0,
            )
            if profile.density is not None:
                scaled = profile.density / np.max(profile.density) * 0.42
                axis.fill_between(
                    grid,
                    y_base,
                    y_base + scaled,
                    facecolor=color,
                    edgecolor=color,
                    linewidth=1.0,
                    alpha=0.32,
                    zorder=2,
                )

            lower, q1, median, q3, upper = box_statistics(values)
            box_y = y_base - 0.27
            axis.plot([lower, upper], [box_y, box_y], color="#30343B", linewidth=1.0, zorder=4)
            axis.plot([lower, lower], [box_y - 0.06, box_y + 0.06], color="#30343B", linewidth=1.0, zorder=4)
            axis.plot([upper, upper], [box_y - 0.06, box_y + 0.06], color="#30343B", linewidth=1.0, zorder=4)
            axis.add_patch(
                Rectangle(
                    (q1, box_y - 0.075),
                    q3 - q1,
                    0.15,
                    facecolor="white",
                    edgecolor="#30343B",
                    linewidth=1.0,
                    zorder=5,
                )
            )
            axis.plot([median, median], [box_y - 0.075, box_y + 0.075], color=color, linewidth=1.6, zorder=6)

            point_order = sorted(
                range(len(observations)),
                key=lambda index: (
                    observations[index].value,
                    observations[index].observation_id,
                    observations[index].source_row,
                ),
            )
            point_values = values[point_order]
            offsets = (
                ((np.arange(values.size, dtype=float) + 1.0) * GOLDEN_FRACTION) % 1.0
                - 0.5
            ) * 0.22
            point_y = y_base - 0.50 + offsets
            point_size = max(5.0, min(14.0, 16.0 - 3.0 * math.log10(values.size + 1)))
            point_alpha = 0.50 if values.size <= 500 else 0.25
            axis.scatter(
                point_values,
                point_y,
                s=point_size,
                color=color,
                alpha=point_alpha,
                edgecolors="none",
                rasterized=values.size > 2000,
                zorder=3,
            )
            tick_labels.append(f"{group}  n={values.size}")

        label_size = 9.0 if maximum_label_length <= 24 else 8.0 if maximum_label_length <= 40 else 7.2
        axis.set_yticks(y_positions, labels=tick_labels, fontsize=label_size)
        axis.tick_params(axis="y", length=0, pad=7)
        axis.tick_params(axis="x", labelsize=8.5, colors="#4A5058")
        axis.set_xlim(x_limits)
        axis.set_ylim(-0.78, len(groups) - 0.47)
        axis.grid(axis="x", color="#E7EAF0", linewidth=0.65)
        axis.set_axisbelow(True)
        for side in ("top", "right", "left"):
            axis.spines[side].set_visible(False)
        axis.spines["bottom"].set_color("#747B85")
        if data.has_facet:
            axis.set_title(facet, loc="left", fontsize=11, fontweight="semibold", pad=8)

    for axis in axes_flat[len(data.facet_order) :]:
        axis.set_visible(False)

    subtitle = (
        f"{len(data.observations)} observations · {len(data.group_order)} groups · "
        f"{len(data.facet_order)} facet{'s' if len(data.facet_order) != 1 else ''}"
    )
    figure.suptitle(title, x=0.035, y=0.988, ha="left", fontsize=15, fontweight="semibold")
    figure.text(0.035, 0.953, subtitle, ha="left", va="top", fontsize=9, color="#59616B")
    figure.supxlabel(x_label, x=0.52, y=0.040, fontsize=10)
    figure.text(
        0.035,
        0.012,
        "Each KDE is independently scaled within its group; sparse or constant groups omit KDE.",
        ha="left",
        va="bottom",
        fontsize=7.5,
        color="#68717C",
    )
    figure.tight_layout(rect=(0.02, 0.075, 0.995, 0.915), h_pad=1.4, w_pad=2.2)
    report_data(data, grid)
    return figure


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Draw group-wise raincloud panels from group/value CSV columns."
    )
    parser.add_argument("--input", required=True, type=Path, help="Input CSV path")
    parser.add_argument(
        "--output-prefix",
        required=True,
        type=Path,
        help="Output path without extension; .png and .svg are added",
    )
    parser.add_argument("--title", default=DEFAULT_TITLE, help="Figure title")
    parser.add_argument("--x-label", default=DEFAULT_X_LABEL, help="Horizontal axis label")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output_prefix.suffix.lower() in {".png", ".svg"}:
        print("ERROR: --output-prefix must not include .png or .svg", file=sys.stderr)
        return 2

    try:
        data = read_input(args.input)
        figure = draw_figure(data, args.title, args.x_label)
    except DataContractError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
    png_path = Path(f"{args.output_prefix}.png")
    svg_path = Path(f"{args.output_prefix}.svg")
    figure.savefig(png_path, dpi=300, facecolor="white", bbox_inches="tight")
    figure.savefig(svg_path, facecolor="white", bbox_inches="tight")
    plt.close(figure)
    print(f"Wrote {png_path}")
    print(f"Wrote {svg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
