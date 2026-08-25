#!/usr/bin/env python3
"""Validate a weighted hierarchy and render a publication-ready sunburst."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Wedge

INK = "#20272D"
MUTED = "#66747B"
BG = "#FBFAF7"
EDGE = "#F6F3EE"
PALETTE = ["#C7775A", "#4F8994", "#8A7EA8", "#789864", "#C19A4B", "#A96976"]


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True)
    p.add_argument("--output-prefix", required=True)
    p.add_argument("--title", default="Hierarchical composition")
    p.add_argument("--dpi", type=int, default=320)
    return p.parse_args()


def load_tree(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    required = {"node_id", "parent_id", "label", "value"}
    if not rows or not required.issubset(rows[0]):
        fail(f"CSV must contain {', '.join(sorted(required))}")
    if len(rows) > 120:
        fail("at most 120 nodes are supported")

    nodes, input_order = {}, {}
    for i, row in enumerate(rows, start=2):
        node_id = (row.get("node_id") or "").strip()
        if not node_id or node_id in nodes:
            fail(f"row {i}: node_id must be non-empty and unique")
        label = (row.get("label") or "").strip()
        if not label:
            fail(f"row {i}: label is empty")
        raw_value = (row.get("value") or "").strip()
        value = None
        if raw_value:
            try:
                value = float(raw_value)
            except ValueError:
                fail(f"row {i}: value is not numeric")
            if not math.isfinite(value) or value <= 0:
                fail(f"row {i}: leaf value must be finite and positive")
        raw_order = (row.get("order") or "").strip()
        try:
            order = float(raw_order) if raw_order else float(i)
        except ValueError:
            fail(f"row {i}: order is not numeric")
        nodes[node_id] = {
            "id": node_id,
            "parent": (row.get("parent_id") or "").strip(),
            "label": label,
            "value": value,
            "group": (row.get("color_group") or "").strip(),
            "order": order,
        }
        input_order[node_id] = i

    roots = [n for n in nodes.values() if not n["parent"]]
    if len(roots) != 1:
        fail(f"expected exactly one root, found {len(roots)}")
    root = roots[0]["id"]
    children = defaultdict(list)
    for node in nodes.values():
        if node["id"] == root:
            continue
        if node["parent"] not in nodes:
            fail(f"node {node['id']}: parent_id {node['parent']!r} does not exist")
        children[node["parent"]].append(node["id"])
    for parent in children:
        children[parent].sort(key=lambda n: (nodes[n]["order"], input_order[n]))

    state, depths = {}, {}

    def visit(node_id: str, depth: int) -> None:
        if state.get(node_id) == 1:
            fail(f"cycle detected at node {node_id}")
        if state.get(node_id) == 2:
            return
        state[node_id] = 1
        depths[node_id] = depth
        for child in children[node_id]:
            visit(child, depth + 1)
        state[node_id] = 2

    visit(root, 0)
    if len(state) != len(nodes):
        fail("hierarchy contains nodes that are not reachable from the root")
    if max(depths.values()) > 5:
        fail("at most 5 visible levels are supported")

    totals = {}

    def aggregate(node_id: str) -> float:
        node = nodes[node_id]
        if children[node_id]:
            if node["value"] is not None:
                fail(f"internal node {node_id}: value must be blank to prevent double counting")
            totals[node_id] = sum(aggregate(child) for child in children[node_id])
        else:
            if node["value"] is None:
                fail(f"leaf node {node_id}: value is required")
            totals[node_id] = node["value"]
        return totals[node_id]

    aggregate(root)
    top = children[root]
    if not top:
        fail("root must have at least one child")
    for child, group in zip(top, [nodes[x]["group"] or nodes[x]["label"] for x in top]):
        stack = [child]
        while stack:
            current = stack.pop()
            if not nodes[current]["group"]:
                nodes[current]["group"] = group
            stack.extend(children[current])
    return nodes, children, depths, totals, root


def tint(hex_color: str, amount: float) -> tuple[float, float, float]:
    rgb = mpl.colors.to_rgb(hex_color)
    return tuple((1 - amount) * c + amount for c in rgb)


def render(nodes, children, depths, totals, root: str, title: str, out: Path, dpi: int) -> None:
    groups = []
    for n in nodes.values():
        if n["group"] and n["group"] not in groups:
            groups.append(n["group"])
    colors = {g: PALETTE[i % len(PALETTE)] for i, g in enumerate(groups)}
    max_depth = max(depths.values())
    inner, ring = 0.24, 0.72 / max_depth
    sectors = []

    def allocate(node_id: str, start: float, end: float) -> None:
        for child in children[node_id]:
            span = (end - start) * totals[child] / totals[node_id]
            sectors.append((child, start, start + span))
            allocate(child, start, start + span)
            start += span

    allocate(root, 90.0, 450.0)
    fig, ax = plt.subplots(figsize=(8.6, 7.2), facecolor=BG)
    ax.set_facecolor(BG)
    for node_id, start, end in sectors:
        depth = depths[node_id]
        base = colors[nodes[node_id]["group"]]
        face = tint(base, min(0.38, 0.10 * (depth - 1)))
        wedge = Wedge((0, 0), inner + depth * ring, start, end,
                      width=ring * 0.95, facecolor=face, edgecolor=EDGE, linewidth=1.25)
        ax.add_patch(wedge)
        span = end - start
        if span >= (11 if depth == 1 else 16):
            angle = math.radians((start + end) / 2)
            radius = inner + (depth - 0.5) * ring
            ax.text(radius * math.cos(angle), radius * math.sin(angle), nodes[node_id]["label"],
                    ha="center", va="center", color=INK, fontsize=9 if depth == 1 else 7.5,
                    fontweight="semibold" if depth == 1 else "normal")
    ax.add_patch(Circle((0, 0), inner * 0.92, facecolor="#FFFFFF", edgecolor="#E4E0D9", linewidth=1.0))
    ax.text(0, 0.025, nodes[root]["label"], ha="center", va="center", fontsize=10,
            color=INK, fontweight="semibold")
    ax.text(0, -0.055, f"Total {totals[root]:g}", ha="center", va="center", fontsize=8, color=MUTED)
    fig.suptitle(title, x=0.08, y=0.965, ha="left", fontsize=18, fontweight="semibold", color=INK)
    fig.text(0.08, 0.925, "Sector area is aggregated from positive leaf weights; parent values are derived.",
             ha="left", fontsize=9, color=MUTED)
    ax.set_xlim(-1.08, 1.08)
    ax.set_ylim(-1.08, 1.08)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.subplots_adjust(left=0.06, right=0.94, top=0.89, bottom=0.05)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out.with_suffix(".png"), dpi=dpi, facecolor=BG)
    fig.savefig(out.with_suffix(".svg"), facecolor=BG)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    nodes, children, depths, totals, root = load_tree(Path(args.input))
    render(nodes, children, depths, totals, root, args.title, Path(args.output_prefix), args.dpi)
    leaves = sum(not children[n] for n in nodes)
    print(f"Validated {len(nodes)} nodes and {leaves} leaves; derived root total {totals[root]:g}; excluded rows: 0.")


if __name__ == "__main__":
    main()
