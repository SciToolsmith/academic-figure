from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpecFromSubplotSpec
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter, FixedLocator


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "cox_forest_data.csv"
OUTPUT_PATH = BASE_DIR / "cox_forest_plot.png"
FONT_STACK = ["Arial", "Helvetica", "DejaVu Sans"]


def format_number(value):
    if value >= 100:
        return f"{value:.0f}"
    if value >= 10:
        return f"{value:.1f}".rstrip("0").rstrip(".")
    if value >= 1:
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{value:.3f}".rstrip("0").rstrip(".")


def format_p(value):
    if pd.isna(value):
        return ""
    if value < 0.001:
        return "<0.001"
    return f"{value:.3f}".rstrip("0").rstrip(".")


def add_row_background(ax, y, color):
    x0, x1 = ax.get_xlim()
    ax.add_patch(Rectangle((x0, y - 0.48), x1 - x0, 0.96, facecolor=color, edgecolor="none", zorder=0))


def draw_panel(fig, slot, frame, title):
    layout = GridSpecFromSubplotSpec(1, 3, subplot_spec=slot, width_ratios=[2.55, 2.35, 2.45], wspace=0.02)
    label_ax = fig.add_subplot(layout[0, 0])
    forest_ax = fig.add_subplot(layout[0, 1])
    stats_ax = fig.add_subplot(layout[0, 2])
    axes = [label_ax, forest_ax, stats_ax]
    row_count = len(frame)
    row_y = np.arange(row_count, 0, -1, dtype=float)
    for ax in axes:
        ax.set_ylim(0.15, row_count + 2.25)
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
    label_ax.set_xlim(0, 1)
    stats_ax.set_xlim(0, 1)
    forest_ax.set_xscale("log")
    forest_ax.set_xlim(0.35, 12.5)
    forest_ax.xaxis.set_major_locator(FixedLocator([0.5, 1, 2, 5, 10]))
    forest_ax.xaxis.set_major_formatter(FuncFormatter(lambda value, position: format_number(value)))
    forest_ax.tick_params(axis="x", colors="#52606d", labelsize=9, length=4, width=0.8)
    forest_ax.grid(axis="x", color="#d9e0e5", linewidth=0.7, zorder=0)
    forest_ax.axvline(1, color="#5d6973", linewidth=1.0, linestyle=(0, (4, 4)), zorder=1)
    label_ax.set_xticks([])
    stats_ax.set_xticks([])
    header_y = row_count + 0.68
    title_y = row_count + 1.65
    label_ax.text(0.0, title_y, title, fontsize=15, fontweight=600, color="#18232c", va="center")
    label_ax.text(0.02, header_y, "Subgroup", fontsize=9.5, fontweight=600, color="#46545f", va="center")
    label_ax.text(0.92, header_y, "N", fontsize=9.5, fontweight=600, color="#46545f", va="center", ha="right")
    forest_ax.text(0.5, header_y, "Hazard ratio", fontsize=9.5, fontweight=600, color="#46545f", va="center", ha="center")
    stats_ax.text(0.02, header_y, "HR (95% CI)", fontsize=9.5, fontweight=600, color="#46545f", va="center")
    stats_ax.text(0.98, header_y, "P value", fontsize=9.5, fontweight=600, color="#46545f", va="center", ha="right")
    for index, (_, row) in enumerate(frame.iterrows()):
        y = row_y[index]
        row_type = row["row_type"]
        if row_type == "header":
            background = "#e5edf1"
        elif index % 2 == 0:
            background = "#f5f7f8"
        else:
            background = "#ffffff"
        for ax in axes:
            add_row_background(ax, y, background)
        indent = 0.08 if row_type in {"reference", "level"} else 0.02
        label_ax.text(indent, y, row["subgroup"], fontsize=9.5, color="#1e2a32", va="center", fontweight=600 if row_type == "header" else 400)
        if not pd.isna(row["n"]):
            label_ax.text(0.92, y, f"{int(row['n'])}", fontsize=9.3, color="#38454f", va="center", ha="right")
        if row_type == "header":
            continue
        hr = float(row["hr"])
        lower = float(row["lower"])
        upper = float(row["upper"])
        p_value = row["p_value"]
        significant = not pd.isna(p_value) and p_value < 0.05
        marker_color = "#167c80" if significant else "#344b5c"
        if row_type == "reference":
            forest_ax.scatter([hr], [y], marker="o", s=34, facecolor="#ffffff", edgecolor=marker_color, linewidth=1.3, zorder=4)
            ci_text = "Reference"
        else:
            forest_ax.errorbar(hr, y, xerr=np.array([[hr - lower], [upper - hr]]), fmt="s", markersize=5.8, markerfacecolor=marker_color, markeredgecolor=marker_color, ecolor=marker_color, elinewidth=1.35, capsize=3.2, capthick=1.1, zorder=4)
            ci_text = f"{format_number(hr)} ({format_number(lower)}-{format_number(upper)})"
        stats_ax.text(0.02, y, ci_text, fontsize=9.2, color="#26343d", va="center")
        stats_ax.text(0.98, y, format_p(p_value), fontsize=9.2, color="#26343d", va="center", ha="right")
    forest_ax.set_xlabel("Hazard ratio (log scale)", fontsize=9.2, color="#46545f", labelpad=7)
    return axes


def main():
    plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": FONT_STACK, "axes.unicode_minus": False, "savefig.facecolor": "white"})
    data = pd.read_csv(DATA_PATH)
    fig = plt.figure(figsize=(12.8, 13.6), facecolor="white")
    outer = fig.add_gridspec(2, 1, left=0.055, right=0.98, top=0.885, bottom=0.055, hspace=0.10)
    draw_panel(fig, outer[0, 0], data[data["model"] == "Univariate"].reset_index(drop=True), "Univariate analysis")
    draw_panel(fig, outer[1, 0], data[data["model"] == "Multivariate"].reset_index(drop=True), "Multivariate analysis")
    fig.suptitle("Cox proportional hazards analysis", x=0.055, y=0.968, ha="left", fontsize=22, fontweight=600, color="#17232c")
    fig.text(0.055, 0.938, "Effect estimates with 95% confidence intervals", ha="left", fontsize=11.5, color="#667782")
    fig.savefig(OUTPUT_PATH, dpi=300, bbox_inches="tight", pad_inches=0.16)
    plt.close(fig)


if __name__ == "__main__":
    main()
