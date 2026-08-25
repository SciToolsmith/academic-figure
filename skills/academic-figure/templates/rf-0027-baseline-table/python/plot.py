#!/usr/bin/env python3
"""Render a schema-driven descriptive baseline table."""

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
matplotlib.rcParams["svg.fonttype"] = "none"

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np


MAX_GROUP_COLUMNS = 6
MAX_DISPLAY_ROWS = 40


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class VariableSpec:
    variable: str
    label: str
    kind: str
    levels: tuple[str, ...]
    summary: str
    decimals: int


@dataclass(frozen=True)
class TableRow:
    kind: str
    label: str
    cells: tuple[str, ...]


def ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def read_schema(path: Path) -> tuple[VariableSpec, ...]:
    if not path.is_file():
        raise ContractError(f"schema file does not exist: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = ["variable", "label", "type", "levels", "summary", "decimals"]
        if reader.fieldnames is None or any(name not in reader.fieldnames for name in required):
            raise ContractError("schema must contain: " + ", ".join(required))
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ContractError("schema contains duplicate column names")
        specs: list[VariableSpec] = []
        for row_number, row in enumerate(reader, start=2):
            variable = (row.get("variable") or "").strip()
            label = (row.get("label") or "").strip()
            kind = (row.get("type") or "").strip()
            levels_text = (row.get("levels") or "").strip()
            summary = (row.get("summary") or "").strip()
            decimals_text = (row.get("decimals") or "").strip()
            if not variable or not label:
                raise ContractError(f"schema row {row_number}: variable and label are required")
            if variable in {"id", "group"}:
                raise ContractError(f"schema row {row_number}: reserved variable {variable!r}")
            if kind not in {"continuous", "categorical"}:
                raise ContractError(f"schema row {row_number}: type must be continuous or categorical")
            try:
                decimals = int(decimals_text)
            except ValueError as error:
                raise ContractError(f"schema row {row_number}: decimals must be an integer") from error
            if decimals < 0 or decimals > 6:
                raise ContractError(f"schema row {row_number}: decimals must be between 0 and 6")
            levels = tuple(part.strip() for part in levels_text.split("|") if part.strip())
            if kind == "continuous":
                if levels:
                    raise ContractError(f"schema row {row_number}: continuous levels must be empty")
                if summary not in {"mean_sd", "median_iqr"}:
                    raise ContractError(f"schema row {row_number}: continuous summary must be mean_sd or median_iqr")
            else:
                if not levels or len(levels) != len(set(levels)):
                    raise ContractError(f"schema row {row_number}: categorical levels must be unique and pipe-delimited")
                if summary != "n_percent_nonmissing":
                    raise ContractError(f"schema row {row_number}: categorical summary must be n_percent_nonmissing")
            specs.append(VariableSpec(variable, label, kind, levels, summary, decimals))
    if not specs:
        raise ContractError("schema contains no variables")
    if len({spec.variable for spec in specs}) != len(specs):
        raise ContractError("schema variable names must be unique")
    return tuple(specs)


def read_data(path: Path, specs: tuple[VariableSpec, ...]) -> list[dict[str, object]]:
    if not path.is_file():
        raise ContractError(f"input file does not exist: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ContractError("input must contain a header row")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ContractError("input contains duplicate column names")
        required = ["id", "group", *[spec.variable for spec in specs]]
        missing = [name for name in required if name not in reader.fieldnames]
        if missing:
            raise ContractError("input is missing schema field(s): " + ", ".join(missing))
        records: list[dict[str, object]] = []
        errors: list[str] = []
        for row_number, row in enumerate(reader, start=2):
            subject_id = (row.get("id") or "").strip()
            group = (row.get("group") or "").strip()
            if not subject_id or not group:
                errors.append(f"row {row_number}: id and group must be non-empty")
                continue
            record: dict[str, object] = {"id": subject_id, "group": group}
            for spec in specs:
                text = (row.get(spec.variable) or "").strip()
                if text == "":
                    record[spec.variable] = None
                elif spec.kind == "continuous":
                    try:
                        value = float(text)
                    except ValueError:
                        errors.append(f"row {row_number}: {spec.variable} is not numeric")
                        value = math.nan
                    if not math.isfinite(value):
                        errors.append(f"row {row_number}: {spec.variable} must be finite")
                    record[spec.variable] = value
                else:
                    if text not in spec.levels:
                        errors.append(f"row {row_number}: {spec.variable}={text!r} is not declared in schema levels")
                    record[spec.variable] = text
            records.append(record)
    if errors:
        raise ContractError("input violates the typed schema:\n  - " + "\n  - ".join(errors[:10]))
    if not records:
        raise ContractError("input contains no subjects")
    ids = [str(record["id"]) for record in records]
    if len(ids) != len(set(ids)):
        raise ContractError("id must be unique: one input row per subject")
    return records


def group_columns(records: list[dict[str, object]], include_overall: bool):
    order = ordered_unique(str(record["group"]) for record in records)
    columns = [(group, [record for record in records if record["group"] == group]) for group in order]
    if include_overall:
        if "Overall" in order:
            raise ContractError("group label 'Overall' conflicts with --include-overall true")
        columns.append(("Overall", records))
    if len(columns) > MAX_GROUP_COLUMNS:
        raise ContractError(
            f"table would have {len(columns)} group columns; maximum is {MAX_GROUP_COLUMNS}. "
            "Split the table using a scientifically defined grouping."
        )
    return columns


def number(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}"


def build_rows(specs: tuple[VariableSpec, ...], columns) -> tuple[TableRow, ...]:
    rows: list[TableRow] = []
    for spec in specs:
        availability = []
        for _, records in columns:
            available = sum(record[spec.variable] is not None for record in records)
            availability.append(f"available {available}/{len(records)}; missing {len(records) - available}")
        rows.append(TableRow("section", spec.label, tuple(availability)))
        if spec.kind == "continuous":
            label = "Mean (SD)" if spec.summary == "mean_sd" else "Median [Q1, Q3]"
            cells = []
            for _, records in columns:
                values = np.asarray(
                    [float(record[spec.variable]) for record in records if record[spec.variable] is not None],
                    dtype=float,
                )
                if not values.size:
                    cells.append("NA")
                elif spec.summary == "mean_sd":
                    sd_text = number(float(np.std(values, ddof=1)), spec.decimals) if values.size > 1 else "NA"
                    cells.append(f"{number(float(np.mean(values)), spec.decimals)} ({sd_text})")
                else:
                    q1, median, q3 = np.quantile(values, (0.25, 0.5, 0.75), method="linear")
                    cells.append(
                        f"{number(float(median), spec.decimals)} "
                        f"[{number(float(q1), spec.decimals)}, {number(float(q3), spec.decimals)}]"
                    )
            rows.append(TableRow("data", label, tuple(cells)))
        else:
            for level in spec.levels:
                cells = []
                for _, records in columns:
                    available = [record[spec.variable] for record in records if record[spec.variable] is not None]
                    count = sum(value == level for value in available)
                    percent = 100.0 * count / len(available) if available else math.nan
                    cells.append(f"{count}/{len(available)} ({percent:.1f}%)" if available else "0/0 (NA)")
                rows.append(TableRow("data", level, tuple(cells)))
    if len(rows) > MAX_DISPLAY_ROWS:
        raise ContractError(
            f"schema expands to {len(rows)} display rows; maximum is {MAX_DISPLAY_ROWS}. "
            "Split variables into themed tables rather than shrinking text."
        )
    return tuple(rows)


def draw_table(title: str, columns, rows: tuple[TableRow, ...]) -> plt.Figure:
    maximum_label = max(len(row.label) for row in rows)
    width = min(20.0, max(8.5, 4.6 + 2.1 * len(columns) + 0.045 * maximum_label))
    height = max(5.0, 2.4 + 0.42 * (len(rows) + 1))
    figure = plt.figure(figsize=(width, height), facecolor="white")
    axis = figure.add_axes([0, 0, 1, 1])
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")
    colors = {
        "ink": "#17212B", "muted": "#617080", "header": "#17354D",
        "section": "#EAF3F2", "stripe": "#F7F9FA", "line": "#D8E0E5", "white": "#FFFFFF"
    }
    left, right, top, bottom = 0.035, 0.975, 0.865, 0.105
    label_fraction = min(0.44, max(0.30, 0.28 + 0.004 * maximum_label))
    label_right = left + (right - left) * label_fraction
    data_width = (right - label_right) / len(columns)
    edges = [left, label_right] + [label_right + data_width * index for index in range(1, len(columns) + 1)]
    units = [1.28] + [1.05 if row.kind == "section" else 1.0 for row in rows]
    unit_height = (top - bottom) / sum(units)

    axis.text(left, 0.962, title, ha="left", va="top", fontsize=18, fontweight="semibold", color=colors["ink"])
    axis.text(
        left, 0.920,
        f"{sum(len(records) for label, records in columns if label != 'Overall')} subject rows · "
        f"{len(columns)} displayed group columns · descriptive summaries only",
        ha="left", va="top", fontsize=9.5, color=colors["muted"]
    )
    y = top
    header_height = units[0] * unit_height
    axis.add_patch(Rectangle((left, y - header_height), right - left, header_height, color=colors["header"], ec="none"))
    axis.text(left + 0.012, y - header_height / 2, "Variable / summary", ha="left", va="center", fontsize=10, fontweight="bold", color="white")
    for index, (label, records) in enumerate(columns):
        center = (edges[index + 1] + edges[index + 2]) / 2
        axis.text(center, y - header_height / 2, f"{label}\nN={len(records)}", ha="center", va="center", fontsize=9.3, fontweight="bold", color="white")
    y -= header_height
    data_index = 0
    for row, weight in zip(rows, units[1:]):
        row_height = weight * unit_height
        fill = colors["section"] if row.kind == "section" else colors["stripe"] if data_index % 2 else colors["white"]
        axis.add_patch(Rectangle((left, y - row_height), right - left, row_height, color=fill, ec="none"))
        axis.plot([left, right], [y - row_height, y - row_height], color=colors["line"], lw=0.65)
        axis.text(
            left + (0.012 if row.kind == "section" else 0.022), y - row_height / 2, row.label,
            ha="left", va="center", fontsize=9.2, fontweight="bold" if row.kind == "section" else "normal", color=colors["ink"]
        )
        for index, cell in enumerate(row.cells):
            center = (edges[index + 1] + edges[index + 2]) / 2
            axis.text(center, y - row_height / 2, cell, ha="center", va="center", fontsize=7.9 if row.kind == "section" else 8.8, color=colors["muted"] if row.kind == "section" else colors["ink"])
        if row.kind == "data":
            data_index += 1
        y -= row_height
    axis.add_patch(Rectangle((left, bottom), right - left, top - bottom, fill=False, ec=colors["header"], lw=1.0))
    axis.text(
        left, 0.060,
        "Categorical percentages use each variable's non-missing denominator. Continuous summaries exclude missing values. "
        "SD is sample SD; quartiles use linear interpolation. No P values or SMD are computed.",
        ha="left", va="top", fontsize=8.1, color=colors["muted"]
    )
    return figure


def report(records, specs, columns) -> None:
    missing_cells = sum(record[spec.variable] is None for record in records for spec in specs)
    print(
        f"Loaded {len(records)} unique subject rows: {len(columns)} displayed group column(s), "
        f"{len(specs)} typed variable(s), {missing_cells} missing value cell(s); 0 subject rows excluded."
    )
    for spec in specs:
        print(f"variable={spec.variable} | type={spec.kind} | summary={spec.summary}")
        for label, group_records in columns:
            available = sum(record[spec.variable] is not None for record in group_records)
            print(f"  group={label} | N={len(group_records)} | available={available} | missing={len(group_records)-available}")


def parse_bool(value: str) -> bool:
    if value.lower() not in {"true", "false"}:
        raise argparse.ArgumentTypeError("expected true or false")
    return value.lower() == "true"


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a schema-driven descriptive baseline table.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--output-prefix", required=True, type=Path)
    parser.add_argument("--title", default="Baseline characteristics")
    parser.add_argument("--include-overall", type=parse_bool, default=False)
    args = parser.parse_args()
    if args.output_prefix.suffix.lower() in {".png", ".svg"}:
        print("ERROR: --output-prefix must not include .png or .svg", file=sys.stderr)
        return 2
    try:
        specs = read_schema(args.schema)
        records = read_data(args.input, specs)
        columns = group_columns(records, args.include_overall)
        rows = build_rows(specs, columns)
    except ContractError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    figure = draw_table(args.title, columns, rows)
    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
    png_path = Path(f"{args.output_prefix}.png")
    svg_path = Path(f"{args.output_prefix}.svg")
    figure.savefig(png_path, dpi=320, facecolor="white", bbox_inches="tight")
    figure.savefig(svg_path, facecolor="white", bbox_inches="tight")
    plt.close(figure)
    report(records, specs, columns)
    print(f"Wrote {png_path}")
    print(f"Wrote {svg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
