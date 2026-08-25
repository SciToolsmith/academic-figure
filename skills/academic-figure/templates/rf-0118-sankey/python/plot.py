#!/usr/bin/env python3
"""Render a generic multi-stage weighted Sankey diagram from CSV data."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import OrderedDict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgba
from matplotlib.patches import PathPatch, Rectangle
from matplotlib.path import Path as MplPath


CONFIG = {
    "background": "#FBFAF7",
    "ink": "#20272D",
    "muted": "#637079",
    "grid": "#D9DEDC",
    "node_width": 0.055,
    "png_dpi": 360,
    "palette": [
        "#287D78", "#C84A5B", "#4C78A8", "#C6923B", "#7A6A9D",
        "#5E8C61", "#B06C49", "#587D8D", "#A15D79", "#82734F",
        "#6C7E9B", "#8B6F63", "#4F8A83", "#9B7158",
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Input CSV file")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--stages", help="Comma-separated stage columns; defaults to stage_* columns")
    parser.add_argument("--weight", help="Optional positive numeric weight column")
    parser.add_argument("--title", default="Multi-stage flow overview")
    parser.add_argument("--subtitle")
    parser.add_argument(
        "--order-mode",
        choices=["total", "observed", "alphabetical"],
        default="total",
    )
    return parser.parse_args()


def unique(values: list[str]) -> list[str]:
    return list(OrderedDict.fromkeys(values))


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        if not headers or any(not str(name).strip() for name in headers):
            raise ValueError("CSV must have non-empty, unique column names")
        if len(headers) != len(set(headers)):
            raise ValueError("CSV column names must be unique")
        rows = [dict(row) for row in reader]
    if not rows:
        raise ValueError("Input CSV has no data rows")
    return rows, headers


def resolve_stages(headers: list[str], requested: str | None) -> list[str]:
    stages = [value.strip() for value in requested.split(",")] if requested else [
        value for value in headers if value.startswith("stage_")
    ]
    if len(stages) < 2:
        raise ValueError("Specify at least two stage columns with --stages")
    if len(stages) != len(set(stages)):
        raise ValueError("Stage columns must be unique")
    missing = [value for value in stages if value not in headers]
    if missing:
        raise ValueError(f"Missing stage columns: {', '.join(missing)}")
    return stages


def normalize_rows(
    rows: list[dict[str, str]], stages: list[str], weight_column: str | None, headers: list[str]
) -> list[dict[str, object]]:
    if weight_column and weight_column not in headers:
        raise ValueError(f"Missing weight column: {weight_column}")
    normalized: list[dict[str, object]] = []
    for line_number, source in enumerate(rows, start=2):
        row: dict[str, object] = {}
        for stage in stages:
            value = str(source.get(stage, "") or "").strip()
            if not value:
                raise ValueError(f"Line {line_number}: stage '{stage}' is missing")
            row[stage] = value
        raw_weight = source.get(weight_column, "1") if weight_column else "1"
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Line {line_number}: invalid weight {raw_weight!r}") from exc
        if not math.isfinite(weight) or weight <= 0:
            raise ValueError(f"Line {line_number}: weight must be finite and positive")
        row["_weight"] = weight
        normalized.append(row)
    return normalized


def totals_by(rows: list[dict[str, object]], stage: str) -> OrderedDict[str, float]:
    totals: OrderedDict[str, float] = OrderedDict()
    for row in rows:
        name = str(row[stage])
        totals[name] = totals.get(name, 0.0) + float(row["_weight"])
    return totals


def ordered_nodes(rows: list[dict[str, object]], stage: str, mode: str) -> list[str]:
    totals = totals_by(rows, stage)
    if mode == "total":
        return sorted(totals, key=lambda name: (-totals[name], name.casefold()))
    if mode == "alphabetical":
        return sorted(totals, key=str.casefold)
    return unique(str(row[stage]) for row in rows)


def color_map(rows: list[dict[str, object]], stages: list[str]) -> dict[str, str]:
    names = sorted({str(row[stage]) for row in rows for stage in stages}, key=str.casefold)
    colors = CONFIG["palette"]
    return {name: colors[index % len(colors)] for index, name in enumerate(names)}


def build_flow(rows: list[dict[str, object]], stages: list[str], order_mode: str) -> dict[str, object]:
    total = sum(float(row["_weight"]) for row in rows)
    orders = [ordered_nodes(rows, stage, order_mode) for stage in stages]
    maximum_nodes = max(map(len, orders))
    gap = min(0.014, 0.18 / max(maximum_nodes - 1, 1))
    usable = 0.86
    scale = (usable - gap * (maximum_nodes - 1)) / total
    if scale <= 0:
        raise ValueError("Too many nodes for a readable layout; aggregate explicitly before plotting")
    colors = color_map(rows, stages)

    nodes: list[list[dict[str, object]]] = []
    for stage, order in zip(stages, orders):
        totals = totals_by(rows, stage)
        occupied = total * scale + gap * (len(order) - 1)
        cursor = 0.5 + occupied / 2
        stage_nodes = []
        for name in order:
            value = totals[name]
            stage_nodes.append(
                {
                    "name": name,
                    "value": value,
                    "y1": cursor,
                    "y0": cursor - value * scale,
                    "color": colors[name],
                }
            )
            cursor -= value * scale + gap
        nodes.append(stage_nodes)

    links_by_gap: list[list[dict[str, object]]] = []
    for stage_index in range(len(stages) - 1):
        source_stage, target_stage = stages[stage_index : stage_index + 2]
        grouped: OrderedDict[tuple[str, str], float] = OrderedDict()
        for row in rows:
            key = (str(row[source_stage]), str(row[target_stage]))
            grouped[key] = grouped.get(key, 0.0) + float(row["_weight"])
        source_index = {str(node["name"]): i for i, node in enumerate(nodes[stage_index])}
        target_index = {str(node["name"]): i for i, node in enumerate(nodes[stage_index + 1])}
        links = [
            {
                "source": source,
                "target": target,
                "weight": weight,
                "source_index": source_index[source],
                "target_index": target_index[target],
            }
            for (source, target), weight in grouped.items()
        ]
        source_cursor = {str(node["name"]): float(node["y1"]) for node in nodes[stage_index]}
        for link in sorted(links, key=lambda item: (item["source_index"], item["target_index"])):
            height = float(link["weight"]) * scale
            name = str(link["source"])
            link["sy1"] = source_cursor[name]
            link["sy0"] = source_cursor[name] - height
            source_cursor[name] -= height
        target_cursor = {str(node["name"]): float(node["y1"]) for node in nodes[stage_index + 1]}
        for link in sorted(links, key=lambda item: (item["target_index"], item["source_index"])):
            height = float(link["weight"]) * scale
            name = str(link["target"])
            link["ty1"] = target_cursor[name]
            link["ty0"] = target_cursor[name] - height
            target_cursor[name] -= height
        links_by_gap.append(links)

    return {"stages": stages, "nodes": nodes, "links": links_by_gap, "total": total}


def adjusted_positions(values: list[float], minimum: float, lower: float = 0.03, upper: float = 0.97) -> np.ndarray:
    values_array = np.asarray(values, dtype=float)
    order = np.argsort(values_array)
    if len(values_array) > 1 and minimum * (len(values_array) - 1) > upper - lower:
        placed = np.linspace(lower, upper, len(values_array))
    else:
        placed = np.clip(values_array[order], lower, upper)
        for index in range(1, len(placed)):
            placed[index] = max(placed[index], placed[index - 1] + minimum)
        if len(placed) and placed[-1] > upper:
            placed -= placed[-1] - upper
        if len(placed) and placed[0] < lower:
            placed += lower - placed[0]
    result = np.empty_like(placed)
    result[order] = placed
    return result


def ribbon_patch(x0: float, x1: float, link: dict[str, object], color: str) -> PathPatch:
    control_1 = x0 + 0.42 * (x1 - x0)
    control_2 = x0 + 0.58 * (x1 - x0)
    vertices = [
        (x0, float(link["sy1"])),
        (control_1, float(link["sy1"])),
        (control_2, float(link["ty1"])),
        (x1, float(link["ty1"])),
        (x1, float(link["ty0"])),
        (control_2, float(link["ty0"])),
        (control_1, float(link["sy0"])),
        (x0, float(link["sy0"])),
        (x0, float(link["sy1"])),
    ]
    codes = [
        MplPath.MOVETO,
        MplPath.CURVE4,
        MplPath.CURVE4,
        MplPath.CURVE4,
        MplPath.LINETO,
        MplPath.CURVE4,
        MplPath.CURVE4,
        MplPath.CURVE4,
        MplPath.CLOSEPOLY,
    ]
    return PathPatch(MplPath(vertices, codes), facecolor=to_rgba(color, 0.30), edgecolor="none", zorder=1)


def format_value(value: float, integer: bool) -> str:
    return f"{int(round(value)):,}" if integer else f"{value:,.2f}".rstrip("0").rstrip(".")


def render(flow: dict[str, object], title: str, subtitle: str, output_dir: Path, integer: bool) -> list[Path]:
    stages = list(flow["stages"])
    nodes = list(flow["nodes"])
    links_by_gap = list(flow["links"])
    stage_count = len(stages)
    maximum_nodes = max(len(stage_nodes) for stage_nodes in nodes)
    width = max(9.0, 2.35 * stage_count + 1.4)
    height = min(13.0, max(5.8, 4.2 + 0.25 * maximum_nodes))
    if maximum_nodes > 24:
        print("Warning: more than 24 nodes in one stage; inspect labels at final size", file=sys.stderr)

    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_facecolor(CONFIG["background"])
    ax.set_facecolor(CONFIG["background"])
    x_positions = np.arange(stage_count, dtype=float)
    node_width = float(CONFIG["node_width"])
    lookup = [{str(node["name"]): node for node in stage_nodes} for stage_nodes in nodes]

    for stage_index, links in enumerate(links_by_gap):
        for link in sorted(links, key=lambda item: float(item["weight"]), reverse=True):
            source_node = lookup[stage_index][str(link["source"])]
            ax.add_patch(
                ribbon_patch(
                    x_positions[stage_index] + node_width / 2,
                    x_positions[stage_index + 1] - node_width / 2,
                    link,
                    str(source_node["color"]),
                )
            )

    for stage_index, stage_nodes in enumerate(nodes):
        centers = [(float(node["y0"]) + float(node["y1"])) / 2 for node in stage_nodes]
        label_positions = adjusted_positions(centers, 0.032 if len(stage_nodes) <= 20 else 0.025)
        for node, center, label_y in zip(stage_nodes, centers, label_positions):
            height_value = max(float(node["y1"]) - float(node["y0"]), 0.0012)
            ax.add_patch(
                Rectangle(
                    (x_positions[stage_index] - node_width / 2, center - height_value / 2),
                    node_width,
                    height_value,
                    facecolor=str(node["color"]),
                    edgecolor="#FFFFFF",
                    linewidth=0.5,
                    zorder=3,
                )
            )
            put_left = stage_index == 0 or (stage_index not in {stage_count - 1} and stage_index % 2 == 1)
            direction = -1 if put_left else 1
            anchor_x = x_positions[stage_index] + direction * node_width / 2
            text_x = anchor_x + direction * 0.028
            if abs(label_y - center) > 0.004:
                ax.plot([anchor_x, text_x], [center, label_y], color="#8B959D", linewidth=0.4, zorder=4)
            ax.text(
                text_x,
                label_y,
                f"{node['name']}  {format_value(float(node['value']), integer)}",
                ha="right" if put_left else "left",
                va="center",
                fontsize=6.2 if len(stage_nodes) > 20 else 7.2,
                color=CONFIG["ink"],
                zorder=5,
                bbox={"boxstyle": "round,pad=0.12", "facecolor": "#FFFFFF", "edgecolor": "none", "alpha": 0.80},
            )
        ax.text(
            x_positions[stage_index],
            1.015,
            stages[stage_index].replace("_", " ").upper(),
            ha="center",
            va="bottom",
            fontsize=8.2,
            weight="bold",
            color=CONFIG["muted"],
        )

    ax.set_xlim(-0.58, stage_count - 1 + 0.58)
    ax.set_ylim(-0.035, 1.055)
    ax.axis("off")
    fig.suptitle(title, x=0.055, y=0.965, ha="left", fontsize=18, weight="bold", color=CONFIG["ink"])
    fig.text(0.055, 0.92, subtitle, ha="left", va="top", fontsize=9, color=CONFIG["muted"])
    fig.text(
        0.055,
        0.025,
        "Ribbon width is proportional to the supplied positive weight; node values are stage totals.",
        ha="left",
        va="bottom",
        fontsize=7.5,
        color=CONFIG["muted"],
    )
    fig.subplots_adjust(left=0.04, right=0.96, top=0.84, bottom=0.07)

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = [output_dir / "sankey_python.png", output_dir / "sankey_python.svg"]
    fig.savefig(outputs[0], dpi=CONFIG["png_dpi"], facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.10)
    fig.savefig(outputs[1], facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.10)
    plt.close(fig)
    return outputs


def main() -> int:
    args = parse_args()
    try:
        rows, headers = read_csv(args.input)
        stages = resolve_stages(headers, args.stages)
        normalized = normalize_rows(rows, stages, args.weight, headers)
        flow = build_flow(normalized, stages, args.order_mode)
        integer = args.weight is None or all(
            float(row["_weight"]).is_integer() for row in normalized
        )
        subtitle = args.subtitle or (
            f"{len(normalized):,} input paths · {len(stages)} stages · "
            f"total weight = {format_value(float(flow['total']), integer)}"
        )
        outputs = render(flow, args.title, subtitle, args.output_dir, integer)
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
