from pathlib import Path
from collections import Counter
import csv
import numpy as np
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

root = Path(__file__).resolve().parent
subtypes = [
    "CD8 Undefined",
    "CD8 Tissue resident",
    "CD8 Stem-like",
    "CD4 Tissue resident",
    "CD8 IFN-responsive",
    "CD4 T regulatory",
    "CD8 Early activated",
    "CD8 Proliferative",
    "CD8 Chemokine producing",
    "CD8 NK-like",
]
palette = dict(zip(subtypes, ["#AEB5BA", "#B84A3A", "#2E9D75", "#5264B4", "#9CBC42", "#4A94CA", "#DF6B35", "#D5A62F", "#62B867", "#B86CB2"]))
with (root / "data.csv").open(newline="", encoding="utf-8-sig") as handle:
    rows = list(csv.DictReader(handle))
if len(rows) != 172386 or list(rows[0]) != ["Cell", "T_subtype", "Timepoint", "UMAP_1", "UMAP_2"]:
    raise ValueError("Unexpected extracted UMAP data")
if {row["T_subtype"] for row in rows} != set(subtypes):
    raise ValueError("Unexpected T-cell subtype")
x = np.asarray([float(row["UMAP_1"]) for row in rows])
y = np.asarray([float(row["UMAP_2"]) for row in rows])
labels = np.asarray([row["T_subtype"] for row in rows])
timepoints = Counter(row["Timepoint"] for row in rows)
counts = Counter(labels)
mpl.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.edgecolor": "#66747A",
        "axes.linewidth": 0.8,
        "text.color": "#17242C",
        "figure.facecolor": "#F6F5F1",
        "axes.facecolor": "#F6F5F1",
        "savefig.facecolor": "#F6F5F1",
    }
)
figure = plt.figure(figsize=(11.2, 6.6))
grid = figure.add_gridspec(1, 2, width_ratios=[1.62, 0.82], left=0.07, right=0.965, bottom=0.15, top=0.84, wspace=0.23)
axis = figure.add_subplot(grid[0, 0])
summary = figure.add_subplot(grid[0, 1])
for subtype in subtypes:
    index = labels == subtype
    axis.scatter(x[index], y[index], s=1.25, color=palette[subtype], alpha=0.58, linewidth=0, rasterized=True)
    center_x = float(np.median(x[index]))
    center_y = float(np.median(y[index]))
    axis.text(center_x, center_y, subtype.replace(" ", "\n", 1), ha="center", va="center", fontsize=6.3, fontweight="bold", bbox={"boxstyle": "round,pad=0.24", "facecolor": "#FCFBF8", "edgecolor": palette[subtype], "linewidth": 0.75, "alpha": 0.9})
axis.set_xlabel("UMAP 1")
axis.set_ylabel("UMAP 2")
axis.set_aspect("equal", adjustable="datalim")
axis.grid(color="#DADBD6", linewidth=0.45)
axis.spines[["top", "right"]].set_visible(False)
axis.set_title("a   T-cell subtype landscape", loc="left", fontsize=13, fontweight="bold", pad=12)
ordered = sorted(subtypes, key=lambda value: counts[value])
values = [counts[value] for value in ordered]
bars = summary.barh(np.arange(len(ordered)), values, color=[palette[value] for value in ordered], edgecolor="#FFFFFF", linewidth=0.7)
summary.set_yticks(np.arange(len(ordered)))
summary.set_yticklabels(ordered, fontsize=7.6)
summary.set_xlabel("Number of cells")
summary.grid(axis="x", color="#DADBD6", linewidth=0.45)
summary.spines[["top", "right", "left"]].set_visible(False)
summary.tick_params(axis="y", length=0)
summary.set_title("b   Supplied subtype counts", loc="left", fontsize=12, fontweight="bold", pad=12)
for bar, value in zip(bars, values):
    summary.text(bar.get_width() + max(values) * 0.018, bar.get_y() + bar.get_height() / 2, f"{value:,}\n({value / len(rows):.1%})", ha="left", va="center", fontsize=6.8, color="#536168")
summary.set_xlim(0, max(values) * 1.22)
figure.text(0.07, 0.96, "T-cell states in the extracted single-cell UMAP", ha="left", va="top", fontsize=18, fontweight="bold")
figure.text(0.07, 0.915, "All 172,386 cells from the supplied Seurat object are shown; labels mark median subtype positions.", ha="left", va="top", fontsize=9.5, color="#5C696E")
figure.text(0.07, 0.048, f"Transparent input: Cell, T_subtype, Timepoint and UMAP coordinates extracted from tcells_resubset.rds.\nTimepoint counts: post = {timepoints['post']:,}; pre = {timepoints['pre']:,}. No inferential comparisons are made.", ha="left", va="bottom", fontsize=7.9, color="#536168", linespacing=1.35)
figure.savefig(root / "plot_python.png", dpi=360)
plt.close(figure)
