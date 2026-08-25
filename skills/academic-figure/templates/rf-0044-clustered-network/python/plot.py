#!/usr/bin/env python3
"""Render a validated network with supplied coordinates and clusters."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

INK = "#20272D"
MUTED = "#68767D"
BG = "#FBFAF7"
PALETTE = ["#C8755C", "#4E8995", "#887DA5", "#789566", "#BE974A", "#A96775"]


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(2)


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--nodes", required=True)
    p.add_argument("--edges", required=True)
    p.add_argument("--output-prefix", required=True)
    p.add_argument("--title", default="Supplied network structure")
    p.add_argument("--dpi", type=int, default=320)
    return p.parse_args()


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def boolean(raw: str, row: int) -> bool:
    value = raw.strip().lower()
    if value in {"", "false", "0", "no"}:
        return False
    if value in {"true", "1", "yes"}:
        return True
    fail(f"nodes row {row}: show_label must be true or false")


def load(nodes_path: Path, edges_path: Path):
    nr, er = read_csv(nodes_path), read_csv(edges_path)
    nreq, ereq = {"node_id", "label", "x", "y", "cluster"}, {"source", "target"}
    if not nr or not nreq.issubset(nr[0]):
        fail(f"nodes CSV must contain {', '.join(sorted(nreq))}")
    if not er or not ereq.issubset(er[0]):
        fail(f"edges CSV must contain {', '.join(sorted(ereq))}")
    if not 5 <= len(nr) <= 120:
        fail("nodes CSV must contain 5–120 rows")
    if len(er) > 500:
        fail("at most 500 edges are supported")
    nodes = {}
    clusters = []
    for i, row in enumerate(nr, 2):
        nid, label, cluster = [(row.get(k) or "").strip() for k in ("node_id", "label", "cluster")]
        if not nid or nid in nodes or not label or not cluster:
            fail(f"nodes row {i}: node_id must be unique and label/cluster non-empty")
        try:
            x, y = float(row["x"]), float(row["y"])
            size = float((row.get("size") or "1").strip())
        except ValueError:
            fail(f"nodes row {i}: x, y, and size must be numeric")
        if not all(math.isfinite(v) for v in (x, y, size)) or size <= 0:
            fail(f"nodes row {i}: coordinates must be finite and size positive")
        nodes[nid] = {"id": nid, "label": label, "x": x, "y": y, "cluster": cluster,
                      "size": size, "show": boolean(row.get("show_label") or "", i)}
        if cluster not in clusters:
            clusters.append(cluster)
    if len(clusters) > 12:
        fail("at most 12 clusters are supported")
    edges, seen = [], set()
    groups = []
    for i, row in enumerate(er, 2):
        source, target = [(row.get(k) or "").strip() for k in ("source", "target")]
        if source not in nodes or target not in nodes or source == target:
            fail(f"edges row {i}: endpoints must reference two different known nodes")
        key = tuple(sorted((source, target)))
        if key in seen:
            fail(f"edges row {i}: duplicate undirected edge {key[0]}–{key[1]}")
        seen.add(key)
        try:
            weight = float((row.get("weight") or "1").strip())
        except ValueError:
            fail(f"edges row {i}: weight must be numeric")
        if not math.isfinite(weight) or weight <= 0:
            fail(f"edges row {i}: weight must be finite and positive")
        group = (row.get("edge_group") or "edge").strip() or "edge"
        if group not in groups:
            groups.append(group)
        edges.append({"source": source, "target": target, "weight": weight, "group": group})
    return nodes, edges, clusters, groups


def scale(values, low, high):
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5 * (low + high)] * len(values)
    return [low + (v - lo) / (hi - lo) * (high - low) for v in values]


def render(nodes, edges, clusters, groups, title: str, out: Path, dpi: int):
    colors = {g: PALETTE[i % len(PALETTE)] for i, g in enumerate(clusters)}
    line_styles = {g: ("-" if i == 0 else (0, (3, 3))) for i, g in enumerate(groups)}
    widths = scale([e["weight"] for e in edges], 0.7, 2.2)
    fig, ax = plt.subplots(figsize=(9.2, 7.0), facecolor=BG)
    ax.set_facecolor(BG)
    for edge, width in zip(edges, widths):
        a, b = nodes[edge["source"]], nodes[edge["target"]]
        ax.plot([a["x"], b["x"]], [a["y"], b["y"]], color="#91A0A5", alpha=0.42,
                linewidth=width, linestyle=line_styles[edge["group"]], zorder=1)
    sizes = scale([n["size"] for n in nodes.values()], 160, 520)
    for (node, area) in zip(nodes.values(), sizes):
        ax.scatter(node["x"], node["y"], s=area, color=colors[node["cluster"]],
                   edgecolor="white", linewidth=1.4, zorder=3)
        if node["show"]:
            ax.annotate(node["label"], (node["x"], node["y"]), xytext=(0, 12),
                        textcoords="offset points", ha="center", va="bottom", fontsize=8.5,
                        color=INK, fontweight="semibold", zorder=4)
    handles = [Line2D([0], [0], marker="o", color="none", markerfacecolor=colors[g],
                      markeredgecolor="white", markersize=9, label=g) for g in clusters]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.01, 0.99), frameon=False,
              ncol=min(3, len(handles)), fontsize=8.5, handletextpad=0.4, columnspacing=1.2)
    fig.suptitle(title, x=0.075, y=0.965, ha="left", fontsize=18, fontweight="semibold", color=INK)
    fig.text(0.075, 0.925, "Coordinates, clusters, labels and edge weights are supplied; no network inference is performed.",
             fontsize=9, color=MUTED)
    xs, ys = [n["x"] for n in nodes.values()], [n["y"] for n in nodes.values()]
    padx, pady = max(max(xs)-min(xs), 1)*0.18, max(max(ys)-min(ys), 1)*0.18
    ax.set_xlim(min(xs)-padx, max(xs)+padx); ax.set_ylim(min(ys)-pady, max(ys)+pady)
    ax.set_aspect("equal", adjustable="box"); ax.axis("off")
    fig.subplots_adjust(left=0.06, right=0.96, top=0.88, bottom=0.05)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out.with_suffix(".png"), dpi=dpi, facecolor=BG)
    fig.savefig(out.with_suffix(".svg"), facecolor=BG)
    plt.close(fig)


def main():
    a = args()
    nodes, edges, clusters, groups = load(Path(a.nodes), Path(a.edges))
    render(nodes, edges, clusters, groups, a.title, Path(a.output_prefix), a.dpi)
    print(f"Validated {len(nodes)} nodes, {len(edges)} unique undirected edges, and {len(clusters)} supplied clusters; excluded rows: 0.")


if __name__ == "__main__":
    main()
