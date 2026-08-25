#!/usr/bin/env python3
"""Render a validated descriptive relationship matrix as PNG and SVG."""

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
import numpy as np
from matplotlib.lines import Line2D


TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
DEMO_DATA = TEMPLATE_ROOT / "data" / "simulated_fixed_seed_relationships.csv"
MAX_VARIABLES = 8
MAX_GROUPS = 12
MISSING_TOKENS = {"", "NA"}


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
            if any(header is None or header.strip() == "" for header in headers):
                raise ValidationError("Input contains an empty column name")
            if len(set(headers)) != len(headers):
                raise ValidationError("Input contains duplicate column names")
            rows: List[Dict[str, str]] = []
            for line, row in enumerate(reader, start=2):
                if None in row:
                    raise ValidationError("CSV line {} has more values than header columns".format(line))
                clean = {key: (value or "").strip() for key, value in row.items()}
                clean["__line__"] = str(line)
                rows.append(clean)
    except UnicodeDecodeError as exc:
        raise ValidationError("Input must be UTF-8 CSV: {}".format(exc)) from exc
    if not rows:
        raise ValidationError("Input must contain at least one data row")
    return rows, list(headers)


def parse_variables(raw: str) -> List[str]:
    variables = [item.strip() for item in raw.split(",")]
    if any(not item for item in variables):
        raise ValidationError("--variables contains an empty name")
    if len(set(variables)) != len(variables):
        raise ValidationError("--variables contains duplicate names")
    if len(variables) < 2:
        raise ValidationError("Choose at least 2 continuous variables")
    if len(variables) > MAX_VARIABLES:
        raise ValidationError(
            "Relationship matrices are limited to {} variables; received {}. "
            "Preselect variables from the scientific question instead of shrinking an unreadable matrix.".format(
                MAX_VARIABLES, len(variables)
            )
        )
    return variables


def check_provenance(rows: Sequence[Dict[str, str]], headers: Sequence[str]) -> None:
    has_status = "data_status" in headers
    has_seed = "simulation_seed" in headers
    if has_status != has_seed:
        raise ValidationError("data_status and simulation_seed must be supplied together")
    if not has_status:
        return
    values = {(row["data_status"], row["simulation_seed"]) for row in rows}
    if any(not status or not seed for status, seed in values):
        raise ValidationError("Simulation provenance values cannot be empty")
    if len(values) != 1:
        raise ValidationError("Simulation provenance values are inconsistent within the input")


def parse_data(
    rows: Sequence[Dict[str, str]],
    headers: Sequence[str],
    variables: Sequence[str],
    group_column: Optional[str],
) -> Tuple[np.ndarray, List[str], Optional[List[str]], int]:
    required = ["sample_id"] + list(variables)
    if group_column:
        required.append(group_column)
    missing = [column for column in required if column not in headers]
    if missing:
        raise ValidationError("Input is missing required columns: {}".format(", ".join(missing)))
    if "sample_id" in variables or (group_column and group_column in variables):
        raise ValidationError("sample_id and the group column cannot also be continuous variables")

    sample_ids: List[str] = []
    groups: Optional[List[str]] = [] if group_column else None
    matrix = np.full((len(rows), len(variables)), np.nan, dtype=float)
    missing_cells = 0
    problems: List[str] = []
    for row_index, row in enumerate(rows):
        line = row["__line__"]
        sample_id = row["sample_id"]
        if not sample_id:
            problems.append("line {} has an empty sample_id".format(line))
        sample_ids.append(sample_id)
        if group_column and groups is not None:
            group = row[group_column]
            if not group:
                problems.append("line {} has an empty group in {}".format(line, group_column))
            groups.append(group)
        for column_index, variable in enumerate(variables):
            value = row[variable]
            if value in MISSING_TOKENS:
                missing_cells += 1
                continue
            try:
                number = float(value)
            except ValueError:
                problems.append(
                    "line {} column {} must be finite numeric, blank, or NA; got {!r}".format(
                        line, variable, value
                    )
                )
                continue
            if not math.isfinite(number):
                problems.append("line {} column {} must be finite; got {!r}".format(line, variable, value))
                continue
            matrix[row_index, column_index] = number
    duplicates = sorted({item for item in sample_ids if sample_ids.count(item) > 1 and item})
    if duplicates:
        problems.append("duplicate sample_id values: {}".format(", ".join(duplicates[:10])))
    if groups is not None:
        levels = list(dict.fromkeys(groups))
        if len(levels) > MAX_GROUPS:
            problems.append("group column has {} levels; maximum is {}".format(len(levels), MAX_GROUPS))
    if problems:
        shown = problems[:25]
        suffix = "\n  - ... additional errors omitted" if len(problems) > 25 else ""
        raise ValidationError("Input validation failed:\n  - " + "\n  - ".join(shown) + suffix)
    return matrix, sample_ids, groups, missing_cells


def average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    cursor = 0
    while cursor < len(values):
        end = cursor + 1
        while end < len(values) and values[order[end]] == values[order[cursor]]:
            end += 1
        ranks[order[cursor:end]] = (cursor + 1 + end) / 2.0
        cursor = end
    return ranks


def coefficient(x: np.ndarray, y: np.ndarray, method: str) -> float:
    if method == "spearman":
        x = average_ranks(x)
        y = average_ranks(y)
    result = float(np.corrcoef(x, y)[0, 1])
    if not math.isfinite(result):
        raise ValidationError("A descriptive correlation was non-finite after validation")
    return result


def validate_analysis(
    matrix: np.ndarray,
    variables: Sequence[str],
    groups: Optional[Sequence[str]],
    policy: str,
) -> Tuple[np.ndarray, Optional[List[str]], Dict[Tuple[int, int], np.ndarray]]:
    if policy == "complete":
        complete = np.all(np.isfinite(matrix), axis=1)
        plot_matrix = matrix[complete]
        plot_groups = [group for group, keep in zip(groups or [], complete) if keep] if groups is not None else None
        if len(plot_matrix) < 3:
            raise ValidationError("complete policy leaves fewer than 3 rows")
    else:
        plot_matrix = matrix
        plot_groups = list(groups) if groups is not None else None

    for index, variable in enumerate(variables):
        values = plot_matrix[:, index]
        values = values[np.isfinite(values)]
        if len(values) < 3:
            raise ValidationError("variable {} has fewer than 3 usable observations".format(variable))
        if np.ptp(values) == 0:
            raise ValidationError("variable {} has no variation in usable observations".format(variable))

    pair_masks: Dict[Tuple[int, int], np.ndarray] = {}
    for row in range(len(variables)):
        for column in range(row):
            mask = np.isfinite(plot_matrix[:, row]) & np.isfinite(plot_matrix[:, column])
            if int(mask.sum()) < 3:
                raise ValidationError(
                    "variable pair {} / {} has fewer than 3 usable observations".format(
                        variables[column], variables[row]
                    )
                )
            if np.ptp(plot_matrix[mask, row]) == 0 or np.ptp(plot_matrix[mask, column]) == 0:
                raise ValidationError(
                    "variable pair {} / {} has zero variance in its usable observations".format(
                        variables[column], variables[row]
                    )
                )
            pair_masks[(row, column)] = mask
    if plot_groups is not None:
        for level in dict.fromkeys(plot_groups):
            group_mask = np.array([group == level for group in plot_groups], dtype=bool)
            if int(group_mask.sum()) < 2:
                raise ValidationError("group {!r} has fewer than 2 usable rows".format(level))
            for index, variable in enumerate(variables):
                count = int(np.sum(group_mask & np.isfinite(plot_matrix[:, index])))
                if count < 2:
                    raise ValidationError(
                        "group {!r} has fewer than 2 usable values for {}".format(level, variable)
                    )
    return plot_matrix, plot_groups, pair_masks


def render(
    matrix: np.ndarray,
    variables: Sequence[str],
    groups: Optional[Sequence[str]],
    pair_masks: Dict[Tuple[int, int], np.ndarray],
    method: str,
    policy: str,
    output_prefix: Path,
    title: str,
    dpi: int,
) -> Tuple[Path, Path, List[int]]:
    p = len(variables)
    max_label = max(len(variable) for variable in variables)
    width = max(7.0, 1.9 * p + 0.035 * max_label)
    height = max(7.0, 1.9 * p + (0.8 if groups else 0.35))
    label_size = max(7.0, 10.0 - 0.45 * max(0, p - 4))
    fig, axes = plt.subplots(p, p, figsize=(width, height), squeeze=False)
    levels = list(dict.fromkeys(groups)) if groups is not None else ["All samples"]
    palette = plt.get_cmap("tab10" if len(levels) <= 10 else "tab20")
    colors = {level: palette(index % palette.N) for index, level in enumerate(levels)}
    group_array = np.array(groups, dtype=object) if groups is not None else np.array(["All samples"] * len(matrix), dtype=object)
    corr_map = plt.get_cmap("coolwarm")
    pair_counts: List[int] = []

    for row in range(p):
        for column in range(p):
            ax = axes[row, column]
            ax.tick_params(labelsize=max(6.0, label_size - 1), length=2.5, color="#6B7280")
            if row == column:
                values = matrix[:, column]
                for level in levels:
                    subset = values[(group_array == level) & np.isfinite(values)]
                    bins = max(5, min(16, int(math.ceil(math.sqrt(len(subset))))))
                    ax.hist(
                        subset, bins=bins, density=True, histtype="stepfilled",
                        alpha=0.22 if len(levels) > 1 else 0.38,
                        color=colors[level], edgecolor=colors[level], linewidth=1.0,
                    )
                ax.set_title(variables[column], fontsize=label_size, pad=4)
                ax.set_yticks([])
            elif row > column:
                mask = pair_masks[(row, column)]
                for level in levels:
                    subset = mask & (group_array == level)
                    ax.scatter(
                        matrix[subset, column], matrix[subset, row], s=max(10, 22 - p),
                        color=colors[level], alpha=0.78, edgecolors="white", linewidths=0.35,
                    )
            else:
                mask = pair_masks[(column, row)]
                x = matrix[mask, column]
                y = matrix[mask, row]
                value = coefficient(x, y, method)
                n_pair = int(mask.sum())
                pair_counts.append(n_pair)
                ax.set_facecolor(corr_map((value + 1.0) / 2.0, alpha=0.62))
                symbol = "r" if method == "pearson" else "rho"
                ax.text(
                    0.5, 0.57, "{} = {:.2f}".format(symbol, value), transform=ax.transAxes,
                    ha="center", va="center", fontsize=label_size + 1, fontweight="semibold",
                )
                ax.text(
                    0.5, 0.36, "n = {}".format(n_pair), transform=ax.transAxes,
                    ha="center", va="center", fontsize=max(6.5, label_size - 1), color="#374151",
                )
                ax.set_xticks([])
                ax.set_yticks([])
            if row < p - 1:
                ax.tick_params(labelbottom=False)
            else:
                ax.set_xlabel(variables[column], fontsize=label_size, labelpad=5)
            if column > 0:
                ax.tick_params(labelleft=False)
            elif row != column:
                ax.set_ylabel(variables[row], fontsize=label_size, labelpad=5)
            for spine in ax.spines.values():
                spine.set_color("#9CA3AF")
                spine.set_linewidth(0.55)

    fig.suptitle(title, y=0.988, fontsize=14, fontweight="semibold")
    subtitle = "Descriptive {} correlations; missing policy: {}".format(method.capitalize(), policy)
    fig.text(0.5, 0.958, subtitle, ha="center", va="top", fontsize=9, color="#374151")
    top = 0.90
    if groups is not None:
        handles = [
            Line2D([0], [0], marker="o", linestyle="None", markerfacecolor=colors[level],
                   markeredgecolor="white", markersize=6.5, label=level)
            for level in levels
        ]
        fig.legend(
            handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.935),
            ncol=min(5, len(levels)), frameon=False, fontsize=8.5,
        )
        top = 0.875
    fig.text(
        0.5, 0.008, "Exploratory description only; no P values, multiplicity tests, or causal claims.",
        ha="center", va="bottom", fontsize=8, color="#4B5563",
    )
    fig.subplots_adjust(left=0.10, right=0.985, bottom=0.095, top=top, wspace=0.12, hspace=0.12)
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    png_path = Path(str(output_prefix) + ".png")
    svg_path = Path(str(output_prefix) + ".svg")
    fig.savefig(png_path, dpi=dpi, facecolor="white", metadata={"Software": "rf-0049 plot.py"})
    fig.savefig(svg_path, facecolor="white", metadata={"Creator": "rf-0049 plot.py"})
    plt.close(fig)
    return png_path, svg_path, pair_counts


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Draw a descriptive relationship matrix without inferential tests.")
    result.add_argument("--input", type=Path, default=DEMO_DATA)
    result.add_argument("--variables", required=True)
    result.add_argument("--group-column")
    result.add_argument("--correlation-method", choices=["pearson", "spearman"], required=True)
    result.add_argument("--missing-policy", choices=["pairwise", "complete"], required=True)
    result.add_argument("--output-prefix", type=Path, required=True)
    result.add_argument("--title", default="Relationship matrix")
    result.add_argument("--dpi", type=int, default=320)
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if args.dpi < 300 or args.dpi > 1200:
        raise ValidationError("--dpi must be an integer from 300 to 1200")
    if args.output_prefix.suffix.lower() in {".png", ".svg", ".pdf"}:
        raise ValidationError("--output-prefix must not include .png, .svg, or .pdf")
    variables = parse_variables(args.variables)
    rows, headers = read_csv(args.input)
    check_provenance(rows, headers)
    matrix, _, groups, missing_cells = parse_data(rows, headers, variables, args.group_column)
    analysis_matrix, analysis_groups, pair_masks = validate_analysis(
        matrix, variables, groups, args.missing_policy
    )
    png_path, svg_path, pair_counts = render(
        analysis_matrix, variables, analysis_groups, pair_masks,
        args.correlation_method, args.missing_policy, args.output_prefix,
        args.title, args.dpi,
    )
    row_report = (
        "{} complete rows retained".format(len(analysis_matrix))
        if args.missing_policy == "complete"
        else "{} input rows retained with pair-specific availability".format(len(analysis_matrix))
    )
    levels = len(set(analysis_groups)) if analysis_groups is not None else 0
    print("Validated {} input rows and {} variables; missing cells: {}; excluded invalid rows: 0.".format(
        len(rows), len(variables), missing_cells
    ))
    print("Method: {} (descriptive only); missing policy: {}; {}.".format(
        args.correlation_method, args.missing_policy, row_report
    ))
    print("Pairwise n range: {}-{}; group levels: {}.".format(min(pair_counts), max(pair_counts), levels))
    print("No P values, multiplicity adjustments, or causal conclusions were computed.")
    print("Wrote {}".format(png_path))
    print("Wrote {}".format(svg_path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValidationError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        sys.exit(2)
