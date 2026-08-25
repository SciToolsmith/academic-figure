#!/usr/bin/env python3
"""Render supplied embedding coordinates with composition derived from the same rows."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

INK = "#20272D"
MUTED = "#68767D"
BG = "#FBFAF7"
GRID = "#E5E1DA"
PALETTE = ["#C8755C", "#4E8995", "#887DA5", "#789566", "#BE974A", "#A96775", "#5F91B7", "#B87C44"]


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(2)


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True)
    p.add_argument("--output-prefix", required=True)
    p.add_argument("--title", default="Embedding and sample composition")
    p.add_argument("--dpi", type=int, default=320)
    return p.parse_args()


def load(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    req = {"observation_id", "sample_id", "x", "y", "category"}
    if not rows or not req.issubset(rows[0]):
        fail(f"CSV must contain {', '.join(sorted(req))}")
    if len(rows) > 200_000:
        fail("at most 200,000 observations are supported")
    seen, parsed, samples, categories, sample_orders = set(), [], [], [], {}
    for i, row in enumerate(rows, 2):
        oid, sample, category = [(row.get(k) or "").strip() for k in ("observation_id", "sample_id", "category")]
        if not oid or oid in seen or not sample or not category:
            fail(f"row {i}: observation_id must be unique and sample_id/category non-empty")
        seen.add(oid)
        try:
            x, y = float(row["x"]), float(row["y"])
            order = float((row.get("sample_order") or len(samples) + 1))
        except ValueError:
            fail(f"row {i}: x, y, and sample_order must be numeric")
        if not all(math.isfinite(v) for v in (x, y, order)):
            fail(f"row {i}: coordinates and sample_order must be finite")
        if sample in sample_orders and sample_orders[sample] != order:
            fail(f"row {i}: sample_order is inconsistent within sample {sample!r}")
        sample_orders[sample] = order
        if sample not in samples:
            samples.append(sample)
        if category not in categories:
            categories.append(category)
        parsed.append({"id": oid, "sample": sample, "x": x, "y": y, "category": category})
    sample_input_order = {sample: i for i, sample in enumerate(samples)}
    samples.sort(key=lambda s: (sample_orders[s], sample_input_order[s]))
    if not 2 <= len(samples) <= 40 or not 2 <= len(categories) <= 16:
        fail("expected 2–40 samples and 2–16 categories")
    return parsed, samples, categories


def render(rows, samples, categories, title: str, out: Path, dpi: int):
    colors = {c: PALETTE[i % len(PALETTE)] for i, c in enumerate(categories)}
    fig = plt.figure(figsize=(12.0, 6.6), facecolor=BG)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.35, 1], left=0.065, right=0.97, top=0.82, bottom=0.13, wspace=0.24)
    ax, bx = fig.add_subplot(gs[0]), fig.add_subplot(gs[1])
    alpha = 0.78 if len(rows) < 2000 else max(0.15, 1200 / len(rows))
    point_size = 18 if len(rows) < 2000 else max(2.5, 12000 / len(rows))
    for category in categories:
        subset = [r for r in rows if r["category"] == category]
        ax.scatter([r["x"] for r in subset], [r["y"] for r in subset], s=point_size,
                   color=colors[category], alpha=alpha, edgecolor="none", label=category)
    ax.set_xlabel("Embedding axis 1", color=INK); ax.set_ylabel("Embedding axis 2", color=INK)
    ax.set_title("A  Supplied embedding", loc="left", fontsize=11, fontweight="semibold", color=INK, pad=12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#9AA5A9")
    ax.tick_params(colors=MUTED, labelsize=8); ax.set_aspect("equal", adjustable="datalim")
    ax.legend(frameon=False, ncol=2, fontsize=8, loc="upper left", handletextpad=0.3, columnspacing=1.0)

    counts = defaultdict(Counter)
    for row in rows:
        counts[row["sample"]][row["category"]] += 1
    totals = {s: sum(counts[s].values()) for s in samples}
    bottom = np.zeros(len(samples))
    for category in categories:
        vals = np.array([counts[s][category] / totals[s] for s in samples])
        bx.bar(np.arange(len(samples)), vals, bottom=bottom, color=colors[category], width=0.72,
               edgecolor=BG, linewidth=0.6)
        bottom += vals
    bx.set_xticks(np.arange(len(samples)), samples, rotation=35, ha="right")
    bx.set_ylim(0, 1.14); bx.set_yticks([0, .25, .5, .75, 1], ["0", "25", "50", "75", "100"])
    bx.set_ylabel("Composition (%)", color=INK)
    bx.set_title("B  Composition from the same rows", loc="left", fontsize=11, fontweight="semibold", color=INK, pad=12)
    bx.spines[["top", "right"]].set_visible(False); bx.spines[["left", "bottom"]].set_color("#9AA5A9")
    bx.tick_params(colors=MUTED, labelsize=8); bx.yaxis.grid(True, color=GRID, linewidth=0.65); bx.set_axisbelow(True)
    for j, sample in enumerate(samples):
        bx.text(j, 1.035, f"n={totals[sample]}", ha="center", va="bottom", fontsize=7, color=MUTED, rotation=90)

    fig.suptitle(title, x=0.065, y=0.96, ha="left", fontsize=18, fontweight="semibold", color=INK)
    fig.text(0.065, 0.91, f"{len(rows):,} supplied observations · {len(samples)} samples · composition denominators are reported above bars.", fontsize=9, color=MUTED)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out.with_suffix(".png"), dpi=dpi, facecolor=BG)
    fig.savefig(out.with_suffix(".svg"), facecolor=BG)
    plt.close(fig)
    return totals


def main():
    a = parse_args(); rows, samples, categories = load(Path(a.input))
    totals = render(rows, samples, categories, a.title, Path(a.output_prefix), a.dpi)
    print(f"Validated {len(rows)} observations; sample denominators: " + ", ".join(f"{s}={totals[s]}" for s in samples) + "; excluded rows: 0.")


if __name__ == "__main__":
    main()
