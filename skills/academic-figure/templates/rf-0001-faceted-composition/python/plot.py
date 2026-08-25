#!/usr/bin/env python3
"""Render validated faceted stacked compositions without implicit normalization."""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["svg.fonttype"] = "none"

import matplotlib.pyplot as plt
from matplotlib.colors import to_hex
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter
import numpy as np


MAX_COMPONENTS = 20
MAX_SAMPLES_PER_FACET = 60


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class Record:
    facet: str
    sample: str
    component: str
    value: float
    source_row: int


@dataclass(frozen=True)
class ComponentStyle:
    component: str
    label: str
    color: str
    order: int


@dataclass(frozen=True)
class CompositionData:
    records: tuple[Record, ...]
    facet_order: tuple[str, ...]
    component_order: tuple[str, ...]
    styles: dict[str, ComponentStyle]
    input_mode: str
    normalized: bool
    original_totals: dict[tuple[str, str], float]
    sample_order_mode: str


def ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def parse_bool(value: str) -> bool:
    if value.lower() not in {"true", "false"}:
        raise argparse.ArgumentTypeError("expected true or false")
    return value.lower() == "true"


def read_style(path: Path | None, components: tuple[str, ...]) -> tuple[tuple[str, ...], dict[str, ComponentStyle]]:
    if path is None:
        if len(components) <= 10:
            cmap = matplotlib.colormaps["tab10"]
        else:
            cmap = matplotlib.colormaps["tab20"]
        styles = {
            component: ComponentStyle(component, component, to_hex(cmap(index % cmap.N)), index + 1)
            for index, component in enumerate(components)
        }
        return components, styles
    if not path.is_file():
        raise ContractError(f"style file does not exist: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = ["component", "label", "color", "order"]
        if reader.fieldnames is None or any(name not in reader.fieldnames for name in required):
            raise ContractError("style must contain: " + ", ".join(required))
        rows: list[ComponentStyle] = []
        for row_number, row in enumerate(reader, start=2):
            component = (row.get("component") or "").strip()
            label = (row.get("label") or "").strip()
            color = (row.get("color") or "").strip()
            try:
                order = int((row.get("order") or "").strip())
            except ValueError as error:
                raise ContractError(f"style row {row_number}: order must be an integer") from error
            if not component or not label or not re.fullmatch(r"#[0-9A-Fa-f]{6}", color) or order < 1:
                raise ContractError(f"style row {row_number}: invalid component, label, #RRGGBB color, or order")
            rows.append(ComponentStyle(component, label, color.upper(), order))
    if len({row.component for row in rows}) != len(rows) or len({row.order for row in rows}) != len(rows):
        raise ContractError("style component and order values must be unique")
    if len({row.color for row in rows}) != len(rows):
        raise ContractError("style colors must be unique")
    if {row.component for row in rows} != set(components):
        raise ContractError("style must list every observed component exactly once")
    rows.sort(key=lambda row: row.order)
    return tuple(row.component for row in rows), {row.component: row for row in rows}


def read_data(
    path: Path,
    style_path: Path | None,
    input_mode: str,
    normalize: bool,
    sum_tolerance: float,
    sample_order_mode: str,
) -> CompositionData:
    if not path.is_file():
        raise ContractError(f"input file does not exist: {path}")
    if input_mode == "proportion" and normalize:
        raise ContractError("proportion input is already normalized; use --normalize false")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = ["facet", "sample", "component", "value"]
        if reader.fieldnames is None or any(name not in reader.fieldnames for name in required):
            raise ContractError("input must contain: " + ", ".join(required))
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ContractError("input contains duplicate column names")
        records: list[Record] = []
        errors: list[str] = []
        for row_number, row in enumerate(reader, start=2):
            facet = (row.get("facet") or "").strip()
            sample = (row.get("sample") or "").strip()
            component = (row.get("component") or "").strip()
            value_text = (row.get("value") or "").strip()
            if not facet or not sample or not component or not value_text:
                errors.append(f"row {row_number}: facet, sample, component and value are required")
                continue
            try:
                value = float(value_text)
            except ValueError:
                errors.append(f"row {row_number}: value is not numeric")
                continue
            if not math.isfinite(value) or value < 0:
                errors.append(f"row {row_number}: value must be finite and nonnegative")
                continue
            records.append(Record(facet, sample, component, value, row_number))
    if errors:
        raise ContractError("input violates the composition contract:\n  - " + "\n  - ".join(errors[:10]))
    if not records:
        raise ContractError("input contains no composition rows")

    keys: dict[tuple[str, str, str], int] = {}
    for item in records:
        key = (item.facet, item.sample, item.component)
        if key in keys:
            raise ContractError(f"duplicate (facet, sample, component) at rows {keys[key]} and {item.source_row}: {key!r}")
        keys[key] = item.source_row
    components = ordered_unique(item.component for item in records)
    if len(components) > MAX_COMPONENTS:
        raise ContractError(f"found {len(components)} components; maximum readable legend is {MAX_COMPONENTS}")
    facet_order = ordered_unique(item.facet for item in records)
    sample_keys = ordered_unique((item.facet, item.sample) for item in records)
    for facet in facet_order:
        count = len({sample for current_facet, sample in sample_keys if current_facet == facet})
        if count > MAX_SAMPLES_PER_FACET:
            raise ContractError(f"facet {facet!r} has {count} samples; maximum is {MAX_SAMPLES_PER_FACET}")
    for key in sample_keys:
        present = {item.component for item in records if (item.facet, item.sample) == key}
        if present != set(components):
            missing = [component for component in components if component not in present]
            raise ContractError(
                f"sample {key!r} does not contain the full component grid; add explicit zero rows for: "
                + ", ".join(missing)
            )

    original_totals = {
        key: sum(item.value for item in records if (item.facet, item.sample) == key)
        for key in sample_keys
    }
    zero_totals = [key for key, total in original_totals.items() if total <= 0]
    if zero_totals:
        raise ContractError(f"sample {zero_totals[0]!r} has zero total; composition is undefined")
    if input_mode == "proportion":
        bad = [(key, total) for key, total in original_totals.items() if abs(total - 1.0) > sum_tolerance]
        if bad:
            key, total = bad[0]
            raise ContractError(
                f"proportion sample {key!r} sums to {total:.12g}, outside 1 ± {sum_tolerance:g}; "
                "the script will not normalize silently"
            )

    if normalize:
        plot_records = tuple(
            Record(item.facet, item.sample, item.component, item.value / original_totals[(item.facet, item.sample)], item.source_row)
            for item in records
        )
    else:
        plot_records = tuple(records)
    component_order, styles = read_style(style_path, components)
    return CompositionData(
        records=plot_records,
        facet_order=facet_order,
        component_order=component_order,
        styles=styles,
        input_mode=input_mode,
        normalized=normalize,
        original_totals=original_totals,
        sample_order_mode=sample_order_mode,
    )


def samples_for(data: CompositionData, facet: str) -> tuple[str, ...]:
    observed = ordered_unique(item.sample for item in data.records if item.facet == facet)
    if data.sample_order_mode == "input":
        return observed
    if data.sample_order_mode == "alphabetical":
        return tuple(sorted(observed))
    return tuple(sorted(observed, key=lambda sample: (-data.original_totals[(facet, sample)], sample)))


def lookup(data: CompositionData) -> dict[tuple[str, str, str], float]:
    return {(item.facet, item.sample, item.component): item.value for item in data.records}


def geometry(data: CompositionData) -> tuple[int, int, float, float]:
    facet_count = len(data.facet_order)
    if facet_count == 1:
        columns = 1
    elif facet_count in (2, 3):
        columns = facet_count
    elif facet_count == 4:
        columns = 2
    else:
        columns = min(3, facet_count)
    rows = math.ceil(facet_count / columns)
    max_samples = max(len(samples_for(data, facet)) for facet in data.facet_order)
    max_label = max(len(sample) for facet in data.facet_order for sample in samples_for(data, facet))
    panel_width = min(11.0, max(5.2, 3.8 + 0.18 * max_samples + 0.025 * max_label))
    return rows, columns, panel_width * columns + 2.3, 4.8 * rows


def draw(data: CompositionData, title: str, value_label: str) -> plt.Figure:
    rows, columns, width, height = geometry(data)
    figure, axes = plt.subplots(rows, columns, figsize=(width, height), squeeze=False, sharey=True)
    figure.subplots_adjust(left=0.07, right=0.80, bottom=0.17 if rows == 1 else 0.10, top=0.82, wspace=0.12, hspace=0.38)
    axes_flat = axes.ravel()
    values = lookup(data)
    proportion_plot = data.input_mode == "proportion" or data.normalized
    global_max = 1.0 if proportion_plot else max(sum(values[facet, sample, component] for component in data.component_order) for facet in data.facet_order for sample in samples_for(data, facet))

    for panel_index, facet in enumerate(data.facet_order):
        axis = axes_flat[panel_index]
        samples = samples_for(data, facet)
        x = np.arange(len(samples))
        bottom = np.zeros(len(samples))
        for component in data.component_order:
            heights = np.asarray([values[facet, sample, component] for sample in samples])
            axis.bar(
                x, heights, bottom=bottom, width=0.88,
                color=data.styles[component].color, edgecolor="white", linewidth=0.45,
                label=data.styles[component].label,
            )
            bottom += heights
        stride = max(1, math.ceil(len(samples) / 20))
        tick_indices = np.arange(0, len(samples), stride)
        tick_labels = [textwrap.fill(samples[index], width=12) for index in tick_indices]
        axis.set_xticks(tick_indices, labels=tick_labels, rotation=55 if len(samples) > 8 else 35, ha="right", fontsize=7.5)
        axis.set_xlim(-0.55, len(samples) - 0.45)
        axis.set_ylim(0, 1.0 if proportion_plot else global_max * 1.04)
        axis.grid(axis="y", color="#E5E8EB", linewidth=0.65)
        axis.set_axisbelow(True)
        axis.set_title(f"{facet} · {len(samples)} samples", loc="left", fontsize=10.5, fontweight="semibold", pad=7)
        axis.tick_params(axis="y", labelsize=8.2, colors="#4E5965")
        if proportion_plot:
            axis.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        for side in ("top", "right"):
            axis.spines[side].set_visible(False)
        axis.spines["left"].set_color("#6C7680")
        axis.spines["bottom"].set_color("#6C7680")
        if stride > 1:
            axis.text(1.0, -0.23, f"sample labels shown every {stride}", transform=axis.transAxes, ha="right", va="top", fontsize=7, color="#6A737D")

    for axis in axes_flat[len(data.facet_order):]:
        axis.set_visible(False)
    mode_text = "validated proportions; no normalization" if data.input_mode == "proportion" else "raw values normalized per sample" if data.normalized else "raw values; no normalization"
    figure.suptitle(title, x=0.07, y=0.965, ha="left", fontsize=16, fontweight="semibold")
    figure.text(0.07, 0.920, f"{len(data.facet_order)} facets · {len(data.component_order)} components · {mode_text}", ha="left", va="top", fontsize=9.3, color="#5E6872")
    figure.supylabel("Proportion" if proportion_plot else value_label, x=0.018, fontsize=10)
    handles = [Patch(facecolor=data.styles[component].color, edgecolor="none", label=data.styles[component].label) for component in data.component_order]
    legend = figure.legend(
        handles=handles, title="Component", loc="upper left", bbox_to_anchor=(0.82, 0.82),
        frameon=False, fontsize=8.5, title_fontsize=10, ncol=2 if len(handles) > 10 else 1,
        handlelength=1.0, labelspacing=0.5, borderaxespad=0,
    )
    legend._legend_box.align = "left"
    figure.text(
        0.07, 0.025,
        "Each bar is one facet/sample key. All component keys are explicit; omitted components are not treated as zero. "
        f"Sample order: {data.sample_order_mode}.",
        ha="left", va="bottom", fontsize=7.5, color="#66707A",
    )
    return figure


def report(data: CompositionData) -> None:
    totals = np.asarray(list(data.original_totals.values()), dtype=float)
    print(
        f"Loaded {len(data.records)} composition rows: {len(data.facet_order)} facet(s), "
        f"{len(data.original_totals)} sample(s), {len(data.component_order)} component(s); "
        f"input_mode={data.input_mode}, normalized={str(data.normalized).lower()}, 0 rows excluded."
    )
    print(f"original sample totals: min={totals.min():.12g} | max={totals.max():.12g}")
    if data.input_mode == "proportion":
        print(f"maximum absolute deviation from 1: {np.max(np.abs(totals - 1.0)):.12g}")
    for facet in data.facet_order:
        samples = samples_for(data, facet)
        stride = max(1, math.ceil(len(samples) / 20))
        print(f"facet={facet} | samples={len(samples)} | label_stride={stride}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render validated faceted stacked compositions.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--style", type=Path, default=None)
    parser.add_argument("--output-prefix", required=True, type=Path)
    parser.add_argument("--input-mode", choices=("proportion", "value"), required=True)
    parser.add_argument("--normalize", type=parse_bool, required=True)
    parser.add_argument("--sum-tolerance", type=float, default=1e-6)
    parser.add_argument("--sample-order", choices=("input", "alphabetical", "total-desc"), default="input")
    parser.add_argument("--title", default="Faceted composition")
    parser.add_argument("--value-label", default="Value")
    args = parser.parse_args()
    if args.output_prefix.suffix.lower() in {".png", ".svg"}:
        print("ERROR: --output-prefix must not include .png or .svg", file=sys.stderr)
        return 2
    if not math.isfinite(args.sum_tolerance) or args.sum_tolerance < 0:
        print("ERROR: --sum-tolerance must be finite and non-negative", file=sys.stderr)
        return 2
    try:
        data = read_data(args.input, args.style, args.input_mode, args.normalize, args.sum_tolerance, args.sample_order)
    except ContractError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    figure = draw(data, args.title, args.value_label)
    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
    png_path = Path(f"{args.output_prefix}.png")
    svg_path = Path(f"{args.output_prefix}.svg")
    figure.savefig(png_path, dpi=320, facecolor="white", bbox_inches="tight")
    figure.savefig(svg_path, facecolor="white", bbox_inches="tight")
    plt.close(figure)
    report(data)
    print(f"Wrote {png_path}")
    print(f"Wrote {svg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
