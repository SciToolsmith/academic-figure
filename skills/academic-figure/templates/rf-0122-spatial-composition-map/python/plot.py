#!/usr/bin/env python3
"""Render compositional symbols on supplied projected boundaries."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Wedge

INK = "#20272D"
MUTED = "#68767D"
BG = "#FBFAF7"
LAND = "#F0F1EC"
PALETTE = ["#C8755C", "#4E8995", "#887DA5", "#789566", "#BE974A", "#A96775", "#5F91B7", "#B87C44"]


def fail(msg: str):
    print(f"ERROR: {msg}", file=sys.stderr); raise SystemExit(2)


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--composition", required=True); p.add_argument("--boundaries", required=True)
    p.add_argument("--output-prefix", required=True); p.add_argument("--crs-label", required=True)
    p.add_argument("--title", default="Spatial distribution and composition"); p.add_argument("--dpi", type=int, default=320)
    return p.parse_args()


def read(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as f: return list(csv.DictReader(f))


def load(comp_path: Path, boundary_path: Path):
    cr, br = read(comp_path), read(boundary_path)
    creq = {"location_id", "label", "x", "y", "component", "value"}; breq = {"polygon_id", "vertex_order", "x", "y"}
    if not cr or not creq.issubset(cr[0]): fail(f"composition CSV must contain {', '.join(sorted(creq))}")
    if not br or not breq.issubset(br[0]): fail(f"boundaries CSV must contain {', '.join(sorted(breq))}")
    locations, components, seen = {}, [], set()
    for i, row in enumerate(cr, 2):
        lid, label, component = [(row.get(k) or "").strip() for k in ("location_id", "label", "component")]
        if not lid or not label or not component: fail(f"composition row {i}: identifiers and labels must be non-empty")
        key = (lid, component)
        if key in seen: fail(f"composition row {i}: duplicate location/component pair")
        seen.add(key)
        try:
            x, y, value = float(row["x"]), float(row["y"]), float(row["value"])
            order = float((row.get("location_order") or i))
        except ValueError: fail(f"composition row {i}: x, y, value and location_order must be numeric")
        if not all(math.isfinite(v) for v in (x, y, value, order)) or value < 0: fail(f"composition row {i}: coordinates/order must be finite and value nonnegative")
        if lid not in locations:
            locations[lid] = {"id": lid, "label": label, "x": x, "y": y, "order": order, "values": {}}
        loc = locations[lid]
        if (loc["label"], loc["x"], loc["y"], loc["order"]) != (label, x, y, order): fail(f"composition row {i}: metadata is inconsistent within location {lid!r}")
        loc["values"][component] = value
        if component not in components: components.append(component)
    if not 1 <= len(locations) <= 80 or not 1 <= len(components) <= 8: fail("expected 1–80 locations and 1–8 components")
    for loc in locations.values():
        loc["total"] = sum(loc["values"].values())
        if loc["total"] <= 0: fail(f"location {loc['id']}: component total must be positive")
    polygons = defaultdict(list)
    for i, row in enumerate(br, 2):
        pid = (row.get("polygon_id") or "").strip()
        if not pid: fail(f"boundaries row {i}: polygon_id is empty")
        try: order, x, y = float(row["vertex_order"]), float(row["x"]), float(row["y"])
        except ValueError: fail(f"boundaries row {i}: vertex_order, x and y must be numeric")
        if not all(math.isfinite(v) for v in (order, x, y)): fail(f"boundaries row {i}: coordinates/order must be finite")
        polygons[pid].append((order, x, y))
    if any(len(v) < 3 for v in polygons.values()): fail("each polygon must have at least three vertices")
    return sorted(locations.values(), key=lambda x: x["order"]), components, polygons


def render(locations, components, polygons, title, crs, out, dpi):
    xs = [v[1] for poly in polygons.values() for v in poly]; ys = [v[2] for poly in polygons.values() for v in poly]
    span = max(max(xs)-min(xs), max(ys)-min(ys), 1); totals = [l["total"] for l in locations]
    amin, amax = min(totals), max(totals)
    def radius(total):
        area = 0.42 if amax == amin else 0.25 + (total-amin)/(amax-amin)*0.33
        return math.sqrt(area / math.pi) * span * 0.14
    colors = {c: PALETTE[i] for i, c in enumerate(components)}
    fig, ax = plt.subplots(figsize=(10.2, 6.8), facecolor=BG); ax.set_facecolor(BG)
    for poly in polygons.values():
        coords = [(x, y) for _, x, y in sorted(poly)]
        ax.add_patch(Polygon(coords, closed=True, facecolor=LAND, edgecolor="#B9C0BD", linewidth=1.0, zorder=0))
    for loc in locations:
        r = radius(loc["total"]); start = 90
        for component in components:
            value = loc["values"].get(component, 0); end = start + 360*value/loc["total"]
            if value > 0: ax.add_patch(Wedge((loc["x"], loc["y"]), r, start, end, facecolor=colors[component], edgecolor=BG, linewidth=0.8, zorder=3))
            start = end
        ax.add_patch(Wedge((loc["x"], loc["y"]), r, 0, 360, facecolor="none", edgecolor="white", linewidth=0.7, zorder=4))
        ax.text(loc["x"], loc["y"]-r-0.035*span, loc["label"], ha="center", va="top", fontsize=7, color=INK, zorder=5)
    handles = [plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=colors[c], markersize=8, label=c) for c in components]
    ax.legend(handles=handles, frameon=False, loc="upper left", ncol=min(4, len(components)), fontsize=8, handletextpad=0.35, columnspacing=1)
    ax.set_aspect("equal"); ax.set_xlim(min(xs)-.08*span, max(xs)+.08*span); ax.set_ylim(min(ys)-.10*span, max(ys)+.10*span); ax.axis("off")
    fig.suptitle(title, x=0.07, y=0.965, ha="left", fontsize=18, fontweight="semibold", color=INK)
    fig.text(0.07, .92, f"Supplied projected coordinates · {crs} · symbol area encodes location total; sectors encode composition.", fontsize=9, color=MUTED)
    fig.subplots_adjust(left=.05, right=.97, top=.86, bottom=.04)
    out.parent.mkdir(parents=True, exist_ok=True); fig.savefig(out.with_suffix(".png"), dpi=dpi, facecolor=BG); fig.savefig(out.with_suffix(".svg"), facecolor=BG); plt.close(fig)


def main():
    a=parse_args(); locations, components, polygons=load(Path(a.composition), Path(a.boundaries)); render(locations, components, polygons, a.title, a.crs_label, Path(a.output_prefix), a.dpi)
    print(f"Validated {len(locations)} locations, {len(components)} components, and {len(polygons)} supplied polygons; excluded rows: 0.")
if __name__ == "__main__": main()
