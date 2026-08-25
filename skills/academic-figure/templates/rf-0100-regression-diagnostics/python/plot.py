#!/usr/bin/env python3
"""Plot supplied regression values without fitting a model."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data" / "simulated_fixed_seed_supplied_diagnostics.csv"
MAX_GROUPS = 12
MAX_SAMPLES = 5000
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "<", ">", "h", "p", "*"]


class ValidationError(Exception):
    pass


def read_csv(path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    if not path.is_file():
        raise ValidationError("Input file not found: {}".format(path))
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames
            if headers is None:
                raise ValidationError("Input has no CSV header")
            if any(header is None or not header.strip() for header in headers):
                raise ValidationError("Input contains an empty column name")
            if len(set(headers)) != len(headers):
                raise ValidationError("Input contains duplicate column names")
            required = ["sample_id", "x", "y", "fitted", "residual"]
            missing = [column for column in required if column not in headers]
            if missing:
                raise ValidationError("Input is missing columns: {}".format(", ".join(missing)))
            rows: List[Dict[str, str]] = []
            for line, row in enumerate(reader, start=2):
                if None in row:
                    raise ValidationError("CSV line {} has extra values".format(line))
                clean = {key: (value or "").strip() for key, value in row.items()}
                clean["__line__"] = str(line)
                rows.append(clean)
    except UnicodeDecodeError as exc:
        raise ValidationError("Input must be UTF-8 CSV: {}".format(exc)) from exc
    if len(rows) < 5:
        raise ValidationError("At least 5 samples are required")
    if len(rows) > MAX_SAMPLES:
        raise ValidationError("At most {} samples can be rendered; received {}".format(MAX_SAMPLES, len(rows)))
    return rows, list(headers)


def finite(value: str, context: str) -> float:
    if value == "":
        raise ValidationError("{} cannot be empty".format(context))
    try:
        result = float(value)
    except ValueError as exc:
        raise ValidationError("{} must be numeric; got {!r}".format(context, value)) from exc
    if not math.isfinite(result):
        raise ValidationError("{} must be finite; got {!r}".format(context, value))
    return result


def validate(
    rows: Sequence[Dict[str, str]], headers: Sequence[str], group_column: Optional[str]
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, Optional[List[str]]]:
    if group_column and group_column not in headers:
        raise ValidationError("Input is missing group column {!r}".format(group_column))
    ids: set[str] = set()
    groups: Optional[List[str]] = [] if group_column else None
    values = {name: [] for name in ("x", "y", "fitted", "residual")}
    problems: List[str] = []
    for row in rows:
        line = row["__line__"]
        sample_id = row["sample_id"]
        if not sample_id or sample_id in ids:
            problems.append("line {} has an empty or duplicate sample_id {!r}".format(line, sample_id))
        ids.add(sample_id)
        if groups is not None and group_column is not None:
            group = row[group_column]
            if not group:
                problems.append("line {} has an empty group".format(line))
            groups.append(group)
        for name in values:
            try:
                values[name].append(finite(row[name], "line {} {}".format(line, name)))
            except ValidationError as exc:
                problems.append(str(exc))
                values[name].append(float("nan"))
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
        raise ValidationError("Input validation failed:\n  - " + "\n  - ".join(shown) + suffix)
    arrays = {name: np.asarray(values[name], dtype=float) for name in values}
    for name in ("x", "y", "fitted"):
        if np.ptp(arrays[name]) == 0:
            raise ValidationError("{} must vary across samples".format(name))
    has_status = "data_status" in headers
    has_seed = "simulation_seed" in headers
    if has_status != has_seed:
        raise ValidationError("data_status and simulation_seed must be supplied together")
    if has_status:
        provenance = {(row["data_status"], row["simulation_seed"]) for row in rows}
        if any(not status or not seed for status, seed in provenance) or len(provenance) != 1:
            raise ValidationError("Simulation provenance must be non-empty and consistent")
    return arrays["x"], arrays["y"], arrays["fitted"], arrays["residual"], groups


def render(
    x: np.ndarray,
    y: np.ndarray,
    fitted: np.ndarray,
    residual: np.ndarray,
    groups: Optional[Sequence[str]],
    output_prefix: Path,
    title: str,
    dpi: int,
) -> Tuple[Path, Path]:
    levels = list(dict.fromkeys(groups)) if groups is not None else ["All samples"]
    group_array = np.asarray(groups if groups is not None else ["All samples"] * len(x), dtype=object)
    palette = plt.get_cmap("tab10" if len(levels) <= 10 else "tab20")
    colors = {level: palette(index % palette.N) for index, level in enumerate(levels)}
    max_group_chars = max(len(level) for level in levels)
    width = max(13.2, 12.8 + 0.04 * max_group_chars)
    height = 7.5 + 0.12 * max(0, len(levels) - 4)
    fig = plt.figure(figsize=(width, height))
    outer = fig.add_gridspec(1, 3, width_ratios=[4.3, 2.5, 4.3], left=0.07, right=0.98, bottom=0.13, top=0.83, wspace=0.30)
    ax_relation = fig.add_subplot(outer[0, 0])
    marginal = outer[0, 1].subgridspec(2, 1, hspace=0.38)
    ax_x = fig.add_subplot(marginal[0, 0])
    ax_y = fig.add_subplot(marginal[1, 0])
    ax_residual = fig.add_subplot(outer[0, 2])
    point_size = max(8.0, min(38.0, 1600.0 / len(x)))

    for index, level in enumerate(levels):
        selected = group_array == level
        ax_relation.scatter(x[selected], y[selected], s=point_size, marker=MARKERS[index],
                            facecolor=colors[level], edgecolor="white", linewidth=0.55, alpha=0.80)
        ax_relation.scatter(x[selected], fitted[selected], s=point_size * 0.85, marker="D",
                            facecolor="none", edgecolor=colors[level], linewidth=0.9, alpha=0.90)
        ax_residual.scatter(fitted[selected], residual[selected], s=point_size, marker=MARKERS[index],
                            facecolor=colors[level], edgecolor="white", linewidth=0.55, alpha=0.80)
    ax_relation.set_xlabel("Supplied x")
    ax_relation.set_ylabel("Supplied y / fitted")
    ax_relation.set_title("A  Relationship", loc="left", fontweight="semibold")
    ax_relation.grid(color="#E5E7EB", linewidth=0.65)
    semantic_handles = [
        Line2D([0], [0], marker="o", linestyle="None", markerfacecolor="#6B7280", markeredgecolor="white", label="Supplied y"),
        Line2D([0], [0], marker="D", linestyle="None", markerfacecolor="none", markeredgecolor="#374151", label="Supplied fitted"),
    ]
    ax_relation.legend(handles=semantic_handles, loc="best", frameon=False, fontsize=8)

    bins = max(8, min(24, int(math.ceil(math.sqrt(len(x))))))
    for level in levels:
        selected = group_array == level
        ax_x.hist(x[selected], bins=bins, density=True, histtype="step", linewidth=1.3, color=colors[level])
        ax_y.hist(y[selected], bins=bins, density=True, histtype="step", linewidth=1.3, color=colors[level])
    ax_x.set_title("B  Marginal distributions", loc="left", fontweight="semibold")
    ax_x.set_xlabel("Supplied x")
    ax_y.set_xlabel("Supplied y")
    for axis in (ax_x, ax_y):
        axis.set_ylabel("Density")
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)

    ax_residual.scatter([], [], alpha=0)
    ax_residual.axhline(0, color="#111827", linestyle="--", linewidth=1.0)
    ax_residual.set_xlabel("Supplied fitted")
    ax_residual.set_ylabel("Supplied residual")
    ax_residual.set_title("C  Residual diagnostic", loc="left", fontweight="semibold")
    ax_residual.grid(color="#E5E7EB", linewidth=0.65)
    for axis in (ax_relation, ax_residual):
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)

    if groups is not None:
        handles = [
            Line2D([0], [0], marker=MARKERS[index], linestyle="None", markerfacecolor=colors[level],
                   markeredgecolor="white", markersize=6, label=level)
            for index, level in enumerate(levels)
        ]
        fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.895),
                   ncol=min(6, len(levels)), frameon=False, fontsize=8.5)
    fig.suptitle(title, y=0.975, fontsize=14, fontweight="semibold")
    fig.text(0.5, 0.94, "All fitted and residual values are supplied; this script fits no model and computes no P values.",
             ha="center", va="top", fontsize=9, color="#374151")
    fig.text(0.5, 0.025, "Descriptive visualization only; supplied residuals are not recomputed or statistically verified.",
             ha="center", va="bottom", fontsize=8, color="#4B5563")
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    png = Path(str(output_prefix) + ".png")
    svg = Path(str(output_prefix) + ".svg")
    fig.savefig(png, dpi=dpi, facecolor="white", metadata={"Software": "rf-0100 plot.py"})
    fig.savefig(svg, facecolor="white", metadata={"Creator": "rf-0100 plot.py"})
    plt.close(fig)
    return png, svg


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Plot supplied regression and residual diagnostics without fitting.")
    result.add_argument("--input", type=Path, default=DEMO)
    result.add_argument("--group-column")
    result.add_argument("--output-prefix", type=Path, required=True)
    result.add_argument("--title", default="Supplied regression diagnostics")
    result.add_argument("--dpi", type=int, default=320)
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if args.dpi < 300 or args.dpi > 1200:
        raise ValidationError("--dpi must be an integer from 300 to 1200")
    if args.output_prefix.suffix.lower() in {".png", ".svg", ".pdf"}:
        raise ValidationError("--output-prefix must not include an extension")
    rows, headers = read_csv(args.input)
    x, y, fitted, residual, groups = validate(rows, headers, args.group_column)
    png, svg = render(x, y, fitted, residual, groups, args.output_prefix, args.title, args.dpi)
    print("Validated {} unique samples; missing diagnostic values: 0; group levels: {}.".format(
        len(x), len(set(groups)) if groups is not None else 0
    ))
    print("Supplied fields plotted: x, y, fitted, residual. Models fitted: 0; P values computed: 0.")
    print("Residuals recomputed or statistically verified: no.")
    print("Wrote {}".format(png))
    print("Wrote {}".format(svg))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValidationError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        sys.exit(2)
