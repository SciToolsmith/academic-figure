#!/usr/bin/env python3
"""Plot a supplied ordered matrix with supplied modules and annotations."""

from __future__ import annotations

import argparse
import csv
import math
import re
import textwrap
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize, TwoSlopeNorm
from matplotlib.patches import Patch, Rectangle
import numpy as np


MATRIX_FIELDS = ("row_id", "column_id", "value", "value_scale")
ROW_FIELDS = ("row_id", "row_label", "row_order", "module", "module_label", "module_order")
COLUMN_FIELDS = ("column_id", "column_label", "column_order")
ANNOTATION_FIELDS = ("module", "annotation", "annotation_value", "annotation_order")
MODULE_COLORS = (
    "#3B6F8F",
    "#A85B4A",
    "#4E7D54",
    "#775A9B",
    "#A87922",
    "#347D80",
    "#92546C",
    "#626E7A",
    "#8A6A42",
    "#4D6BA8",
    "#7B7041",
    "#536D5A",
)


class ContractError(ValueError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot a supplied matrix in supplied order; no clustering or enrichment is performed."
    )
    parser.add_argument("--matrix", required=True, help="Long matrix CSV")
    parser.add_argument("--rows", required=True, help="Row metadata CSV")
    parser.add_argument("--columns", required=True, help="Column metadata CSV")
    parser.add_argument("--annotations", help="Optional supplied module-annotation CSV")
    parser.add_argument("--color-mode", required=True, choices=("diverging", "sequential"))
    parser.add_argument("--color-center", type=float)
    parser.add_argument("--title", default="Supplied ordered matrix and modules")
    parser.add_argument("--output-prefix", required=True)
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


def positive_integer(value: str, field: str, row_number: str) -> int:
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise ContractError(f"row {row_number}: {field} must be a positive integer")
    return int(value)


def require_unique(rows: Sequence[Mapping[str, object]], field: str, source: str) -> None:
    values = [str(row[field]) for row in rows]
    duplicate = next((value for value, count in Counter(values).items() if count > 1), None)
    if duplicate is not None:
        raise ContractError(f"{source}: duplicate {field} {duplicate!r}")


def exact_order(values: Sequence[int], field: str) -> None:
    expected = list(range(1, len(values) + 1))
    if sorted(values) != expected:
        raise ContractError(f"{field} must contain each integer from 1 to {len(values)} exactly once")


def validate_metadata(
    row_rows: Sequence[Dict[str, str]], column_rows: Sequence[Dict[str, str]]
) -> Dict[str, object]:
    rows: List[Dict[str, object]] = []
    for raw in row_rows:
        row_number = raw["__row_number__"]
        for field in ("row_id", "row_label", "module", "module_label"):
            if not raw[field]:
                raise ContractError(f"row metadata row {row_number}: {field} must not be empty")
        if len(raw["row_label"]) > 60:
            raise ContractError(f"row metadata row {row_number}: row_label exceeds 60 characters")
        if len(raw["module_label"]) > 50:
            raise ContractError(f"row metadata row {row_number}: module_label exceeds 50 characters")
        annotation = raw.get("row_annotation", "")
        if len(annotation) > 90:
            raise ContractError(f"row metadata row {row_number}: row_annotation exceeds 90 characters")
        parsed: Dict[str, object] = dict(raw)
        parsed["row_order"] = positive_integer(raw["row_order"], "row_order", row_number)
        parsed["module_order"] = positive_integer(raw["module_order"], "module_order", row_number)
        parsed["row_annotation"] = annotation
        rows.append(parsed)
    require_unique(rows, "row_id", "row metadata")
    exact_order([int(row["row_order"]) for row in rows], "row_order")
    if len(rows) > 60:
        raise ContractError(f"found {len(rows)} rows; the template limit is 60")
    rows.sort(key=lambda row: int(row["row_order"]))

    modules: "OrderedDict[str, Dict[str, object]]" = OrderedDict()
    for row in rows:
        module = str(row["module"])
        current = {"module_label": row["module_label"], "module_order": row["module_order"]}
        if module in modules and modules[module] != current:
            raise ContractError(f"module {module!r} has inconsistent module_label or module_order")
        modules[module] = current
    module_orders = [int(value["module_order"]) for value in modules.values()]
    if len(set(module_orders)) != len(module_orders):
        raise ContractError("module_order must be unique across modules")
    exact_order(module_orders, "module_order")
    if len(modules) > 12:
        raise ContractError(f"found {len(modules)} modules; the template limit is 12")
    observed_blocks: List[str] = []
    for row in rows:
        module = str(row["module"])
        if not observed_blocks or observed_blocks[-1] != module:
            observed_blocks.append(module)
    expected_blocks = [
        module for module, _ in sorted(modules.items(), key=lambda item: int(item[1]["module_order"]))
    ]
    if observed_blocks != expected_blocks:
        raise ContractError(
            "modules must form contiguous row blocks ordered exactly by module_order; "
            f"observed {observed_blocks}, expected {expected_blocks}"
        )

    columns: List[Dict[str, object]] = []
    for raw in column_rows:
        row_number = raw["__row_number__"]
        for field in ("column_id", "column_label"):
            if not raw[field]:
                raise ContractError(f"column metadata row {row_number}: {field} must not be empty")
        if len(raw["column_label"]) > 50:
            raise ContractError(f"column metadata row {row_number}: column_label exceeds 50 characters")
        parsed = dict(raw)
        parsed["column_order"] = positive_integer(raw["column_order"], "column_order", row_number)
        columns.append(parsed)
    require_unique(columns, "column_id", "column metadata")
    exact_order([int(row["column_order"]) for row in columns], "column_order")
    if len(columns) > 40:
        raise ContractError(f"found {len(columns)} columns; the template limit is 40")
    columns.sort(key=lambda row: int(row["column_order"]))
    return {"rows": rows, "columns": columns, "modules": modules}


def validate_matrix(
    raw_rows: Sequence[Dict[str, str]], metadata: Mapping[str, object]
) -> Tuple[np.ndarray, str, List[Dict[str, object]]]:
    rows_meta = list(metadata["rows"])
    columns_meta = list(metadata["columns"])
    row_ids = [str(row["row_id"]) for row in rows_meta]
    column_ids = [str(row["column_id"]) for row in columns_meta]
    allowed_rows, allowed_columns = set(row_ids), set(column_ids)
    parsed_rows: List[Dict[str, object]] = []
    scales: List[str] = []
    keys: Counter[Tuple[str, str]] = Counter()
    for raw in raw_rows:
        row_number = raw["__row_number__"]
        row_id, column_id, scale = raw["row_id"], raw["column_id"], raw["value_scale"]
        if not row_id or not column_id or not scale:
            raise ContractError(f"matrix row {row_number}: row_id, column_id, and value_scale must not be empty")
        if row_id not in allowed_rows:
            raise ContractError(f"matrix row {row_number}: unknown row_id {row_id!r}")
        if column_id not in allowed_columns:
            raise ContractError(f"matrix row {row_number}: unknown column_id {column_id!r}")
        value = finite_number(raw["value"], "value", row_number)
        keys[(row_id, column_id)] += 1
        parsed = dict(raw)
        parsed["value"] = value
        parsed_rows.append(parsed)
        scales.append(scale)
    duplicate = next((key for key, count in keys.items() if count > 1), None)
    if duplicate is not None:
        raise ContractError(f"duplicate matrix (row_id, column_id) key: {duplicate}")
    scale_values = list(OrderedDict.fromkeys(scales))
    if len(scale_values) != 1:
        raise ContractError(f"value_scale must have one value across the matrix; found {scale_values}")
    expected = {(row_id, column_id) for row_id in row_ids for column_id in column_ids}
    missing = expected - set(keys)
    if missing:
        example = sorted(missing)[0]
        raise ContractError(
            f"matrix is incomplete: missing {len(missing)} of {len(expected)} required cells; "
            f"example missing key {example}. Missing cells are not imputed."
        )
    if len(parsed_rows) != len(expected):
        raise ContractError("matrix cell count does not match the declared row-by-column grid")

    row_index = {row_id: index for index, row_id in enumerate(row_ids)}
    column_index = {column_id: index for index, column_id in enumerate(column_ids)}
    matrix = np.empty((len(row_ids), len(column_ids)), dtype=float)
    for row in parsed_rows:
        matrix[row_index[str(row["row_id"])], column_index[str(row["column_id"])]] = float(row["value"])
    return matrix, scale_values[0], parsed_rows


def validate_annotations(
    raw_rows: Sequence[Dict[str, str]], metadata: Mapping[str, object]
) -> List[Dict[str, object]]:
    modules = metadata["modules"]
    annotations: List[Dict[str, object]] = []
    for raw in raw_rows:
        row_number = raw["__row_number__"]
        module, label, value = raw["module"], raw["annotation"], raw["annotation_value"]
        if not module or not label or not value:
            raise ContractError(
                f"annotation row {row_number}: module, annotation, and annotation_value must not be empty"
            )
        if module not in modules:
            raise ContractError(f"annotation row {row_number}: unknown module {module!r}")
        if len(label) > 80 or len(value) > 50:
            raise ContractError(f"annotation row {row_number}: annotation or annotation_value is too long")
        parsed: Dict[str, object] = dict(raw)
        parsed["annotation_order"] = positive_integer(raw["annotation_order"], "annotation_order", row_number)
        annotations.append(parsed)
    if len(annotations) > 30:
        raise ContractError("the annotation file contains more than 30 supplied annotations")
    grouped: Dict[str, List[Dict[str, object]]] = {module: [] for module in modules}
    for row in annotations:
        grouped[str(row["module"])].append(row)
    for module, group_rows in grouped.items():
        if len(group_rows) > 4:
            raise ContractError(f"module {module!r} has more than 4 supplied annotations")
        if group_rows:
            exact_order([int(row["annotation_order"]) for row in group_rows], f"annotation_order within {module}")
    annotations.sort(
        key=lambda row: (
            int(modules[str(row["module"])]["module_order"]), int(row["annotation_order"])
        )
    )
    return annotations


def color_contract(matrix: np.ndarray, mode: str, center: float | None):
    minimum, maximum = float(np.min(matrix)), float(np.max(matrix))
    if minimum == maximum:
        raise ContractError("matrix values are constant; a color scale cannot encode variation")
    if mode == "diverging":
        if center is None or not math.isfinite(center):
            raise ContractError("--color-center is required and must be finite for diverging mode")
        if not minimum < center < maximum:
            raise ContractError(
                f"diverging center {center:g} must lie strictly inside the data range [{minimum:g}, {maximum:g}]"
            )
        span = max(abs(minimum - center), abs(maximum - center))
        vmin, vmax = center - span, center + span
        cmap = LinearSegmentedColormap.from_list("supplied_diverging", ("#2B6CB0", "#F7F7F4", "#C4473D"))
        norm = TwoSlopeNorm(vmin=vmin, vcenter=center, vmax=vmax)
    else:
        if center is not None:
            raise ContractError("--color-center must not be supplied for sequential mode")
        vmin, vmax = minimum, maximum
        cmap = LinearSegmentedColormap.from_list("supplied_sequential", ("#F5F5F1", "#9BC4D4", "#245A7A"))
        norm = Normalize(vmin=vmin, vmax=vmax)
    return cmap, norm, vmin, vmax


def wrapped_row_label(row: Mapping[str, object]) -> str:
    label = textwrap.fill(str(row["row_label"]), width=26)
    annotation = str(row.get("row_annotation", ""))
    if annotation:
        label += "\n" + textwrap.fill(annotation, width=30)
    return label


def module_blocks(rows: Sequence[Mapping[str, object]]) -> List[Tuple[str, int, int]]:
    blocks = []
    start = 0
    while start < len(rows):
        module = str(rows[start]["module"])
        end = start
        while end + 1 < len(rows) and str(rows[end + 1]["module"]) == module:
            end += 1
        blocks.append((module, start, end))
        start = end + 1
    return blocks


def draw_figure(
    matrix: np.ndarray,
    value_scale: str,
    metadata: Mapping[str, object],
    annotations: Sequence[Mapping[str, object]],
    cmap,
    norm,
    vmin: float,
    vmax: float,
    title: str,
) -> plt.Figure:
    rows = list(metadata["rows"])
    columns = list(metadata["columns"])
    modules = metadata["modules"]
    blocks = module_blocks(rows)
    n_rows, n_columns = matrix.shape
    has_row_annotations = any(str(row.get("row_annotation", "")) for row in rows)
    max_row_chars = max(len(str(row["row_label"])) + len(str(row.get("row_annotation", ""))) for row in rows)
    heat_width = min(11.5, max(4.6, 0.46 * n_columns + 1.2))
    annotation_width = 4.2 if annotations else 0
    figure_width = min(19.0, 3.0 + 0.052 * min(max_row_chars, 100) + heat_width + annotation_width)
    figure_height = min(21.5, max(7.0, 3.2 + n_rows * (0.40 if has_row_annotations else 0.31)))
    legend_rows = math.ceil(len(modules) / min(4, len(modules)))
    figure_height += 0.25 * legend_rows

    widths = [0.55, heat_width]
    if annotations:
        widths.append(annotation_width)
    widths.append(0.32)
    fig = plt.figure(figsize=(figure_width, figure_height), facecolor="white")
    grid = fig.add_gridspec(1, len(widths), width_ratios=widths, wspace=0.035)
    track_ax = fig.add_subplot(grid[0, 0])
    heat_ax = fig.add_subplot(grid[0, 1], sharey=track_ax)
    next_index = 2
    annotation_ax = None
    if annotations:
        annotation_ax = fig.add_subplot(grid[0, next_index], sharey=track_ax)
        next_index += 1
    color_ax = fig.add_subplot(grid[0, next_index])
    bottom = 0.18 if n_columns <= 16 else 0.23
    top = max(0.70, 0.84 - 0.028 * (legend_rows - 1))
    fig.subplots_adjust(left=0.20, right=0.965, bottom=bottom, top=top)

    module_colors = {
        module: MODULE_COLORS[index]
        for index, (module, _) in enumerate(
            sorted(modules.items(), key=lambda item: int(item[1]["module_order"]))
        )
    }
    track_ax.set_xlim(0, 1)
    track_ax.set_ylim(n_rows - 0.5, -0.5)
    for module, start, end in blocks:
        color = module_colors[module]
        track_ax.add_patch(Rectangle((0, start - 0.5), 1, end - start + 1, facecolor=color, edgecolor="white", linewidth=1.0))
        track_ax.text(
            0.5,
            (start + end) / 2,
            str(modules[module]["module_order"]),
            color="white",
            ha="center",
            va="center",
            fontsize=8.5,
            fontweight="bold",
        )
    track_ax.set_xticks([])
    track_ax.set_yticks(np.arange(n_rows))
    track_ax.set_yticklabels([wrapped_row_label(row) for row in rows], fontsize=7.6)
    track_ax.tick_params(axis="y", length=0, pad=7)
    track_ax.set_title("Module", fontsize=9, pad=8)
    for spine in track_ax.spines.values():
        spine.set_visible(False)

    image = heat_ax.imshow(matrix, aspect="auto", interpolation="nearest", cmap=cmap, norm=norm, origin="upper")
    heat_ax.set_xlim(-0.5, n_columns - 0.5)
    heat_ax.set_ylim(n_rows - 0.5, -0.5)
    heat_ax.set_xticks(np.arange(n_columns))
    rotation = 45 if max(len(str(column["column_label"])) for column in columns) <= 18 else 60
    heat_ax.set_xticklabels(
        [textwrap.fill(str(column["column_label"]), width=16) for column in columns],
        rotation=rotation,
        ha="right",
        rotation_mode="anchor",
        fontsize=8,
    )
    heat_ax.tick_params(axis="y", left=False, labelleft=False)
    heat_ax.tick_params(axis="x", length=0, pad=6)
    heat_ax.set_title("Matrix in supplied order", fontsize=10, pad=8)
    for module, _, end in blocks[:-1]:
        heat_ax.axhline(end + 0.5, color="white", linewidth=2.0)
    for spine in heat_ax.spines.values():
        spine.set_visible(False)

    if annotation_ax is not None:
        annotation_ax.set_xlim(0, 1)
        annotation_ax.set_ylim(n_rows - 0.5, -0.5)
        annotation_ax.set_xticks([])
        annotation_ax.tick_params(axis="y", left=False, labelleft=False)
        annotation_ax.set_title("Supplied upstream annotations", fontsize=10, pad=8)
        for module, start, end in blocks:
            color = module_colors[module]
            annotation_ax.add_patch(
                Rectangle((0, start - 0.5), 1, end - start + 1, facecolor=color, edgecolor="white", alpha=0.075)
            )
            selected = [row for row in annotations if str(row["module"]) == module]
            if selected:
                lines = [
                    textwrap.fill(f"{row['annotation']} · {row['annotation_value']}", width=42)
                    for row in selected
                ]
                annotation_ax.text(
                    0.035,
                    (start + end) / 2,
                    "\n".join(lines),
                    ha="left",
                    va="center",
                    fontsize=max(6.8, min(8.3, 9.0 - 0.035 * n_rows)),
                    color="#303030",
                )
        for _, _, end in blocks[:-1]:
            annotation_ax.axhline(end + 0.5, color="#B9B9B9", linewidth=0.8)
        for spine in annotation_ax.spines.values():
            spine.set_visible(False)

    colorbar = fig.colorbar(image, cax=color_ax)
    colorbar.set_label(value_scale, fontsize=8.5)
    colorbar.ax.tick_params(labelsize=7.5)
    colorbar.outline.set_linewidth(0.6)

    legend_handles = [
        Patch(
            facecolor=module_colors[module],
            edgecolor="none",
            label=f"{int(info['module_order'])} = {info['module_label']}",
        )
        for module, info in sorted(modules.items(), key=lambda item: int(item[1]["module_order"]))
    ]
    fig.suptitle(title, x=0.20, y=0.978, ha="left", fontsize=15, fontweight="bold")
    fig.text(
        0.20,
        0.943,
        "Rows, columns, modules, and annotation text are supplied upstream; no clustering or enrichment is run.",
        ha="left",
        va="top",
        fontsize=8.5,
        color="#555555",
    )
    fig.legend(
        handles=legend_handles,
        loc="upper center",
        bbox_to_anchor=(0.58, 0.912),
        ncol=min(4, len(legend_handles)),
        frameon=False,
        fontsize=8,
        title="Module key (number = module_order)",
        title_fontsize=8,
    )
    fig.text(
        0.20,
        0.035,
        f"Matrix: {n_rows} rows × {n_columns} columns · value scale: {value_scale} · color domain: [{vmin:g}, {vmax:g}] · no clipping or imputation.",
        ha="left",
        va="bottom",
        fontsize=8,
        color="#555555",
    )
    return fig


def main() -> None:
    args = parse_args()
    try:
        if args.dpi < 150 or args.dpi > 1200:
            raise ContractError("--dpi must be between 150 and 1200")
        row_rows = read_csv(Path(args.rows), ROW_FIELDS)
        column_rows = read_csv(Path(args.columns), COLUMN_FIELDS)
        metadata = validate_metadata(row_rows, column_rows)
        matrix_rows = read_csv(Path(args.matrix), MATRIX_FIELDS)
        matrix, value_scale, parsed_matrix_rows = validate_matrix(matrix_rows, metadata)
        annotations: List[Dict[str, object]] = []
        if args.annotations:
            annotation_rows = read_csv(Path(args.annotations), ANNOTATION_FIELDS)
            annotations = validate_annotations(annotation_rows, metadata)
        cmap, norm, vmin, vmax = color_contract(matrix, args.color_mode, args.color_center)
        figure = draw_figure(matrix, value_scale, metadata, annotations, cmap, norm, vmin, vmax, args.title)
        prefix = Path(args.output_prefix)
        prefix.parent.mkdir(parents=True, exist_ok=True)
        png_path = prefix.with_suffix(".png")
        svg_path = prefix.with_suffix(".svg")
        figure.savefig(png_path, dpi=args.dpi, facecolor="white", bbox_inches="tight")
        figure.savefig(svg_path, facecolor="white", bbox_inches="tight")
        plt.close(figure)
    except ContractError as exc:
        raise SystemExit(f"ERROR: {exc}") from None

    rows = metadata["rows"]
    columns = metadata["columns"]
    modules = metadata["modules"]
    print(
        f"Loaded complete supplied matrix: {len(parsed_matrix_rows)} cells, {len(rows)} row(s), "
        f"{len(columns)} column(s), {len(modules)} module(s); 0 cells excluded or imputed."
    )
    print(
        f"value_scale={value_scale} | color_mode={args.color_mode} | "
        f"color_center={args.color_center if args.color_center is not None else 'none'} | "
        f"color_domain=[{vmin:g}, {vmax:g}] | clipping=false"
    )
    print("row_order=validated | column_order=validated | contiguous_module_blocks=validated | clustering_run=false")
    print(f"supplied_annotations={len(annotations)} | enrichment_run=false")
    print(f"Wrote {png_path}")
    print(f"Wrote {svg_path}")


if __name__ == "__main__":
    main()
