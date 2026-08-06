from pathlib import Path
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd


def find_input(base, name):
    for candidate in (base / name, base / "data" / name):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Required input not found: {name}")


def read_gmt(path, names):
    result = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("\t")
            if fields and fields[0] in names:
                result[fields[0]] = set(fields[2:])
    missing = set(names) - set(result)
    if missing:
        raise ValueError(f"Gene sets missing from GMT: {sorted(missing)}")
    return result


def enrichment_curve(ranked, members):
    scores = ranked["logFC"].to_numpy(float)
    symbols = ranked["external_gene_name"].astype(str).to_numpy()
    hits = np.fromiter((symbol in members for symbol in symbols), dtype=bool)
    hit_count = int(hits.sum())
    if hit_count == 0 or hit_count == len(hits):
        raise ValueError("Gene set must map to at least one but not all ranked genes")
    weights = np.abs(scores)
    hit_total = weights[hits].sum()
    if hit_total <= 0:
        weights = np.ones_like(weights)
        hit_total = weights[hits].sum()
    increments = np.where(hits, weights / hit_total, -1.0 / (len(hits) - hit_count))
    running = np.cumsum(increments)
    high = int(np.argmax(running))
    low = int(np.argmin(running))
    peak = high if abs(running[high]) >= abs(running[low]) else low
    return running, np.flatnonzero(hits) + 1, float(running[peak]), peak + 1, hit_count


def style_axis(axis):
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.spines["left"].set_color("#283333")
    axis.spines["bottom"].set_color("#283333")
    axis.tick_params(colors="#344242", length=3.5, width=0.8)
    axis.grid(axis="y", color="#DDE3E0", linewidth=0.65, alpha=0.75)
    axis.set_axisbelow(True)


def draw_enrichment(axis, running, hits, score, peak, mapped, title, color, panel):
    ranks = np.arange(1, len(running) + 1)
    lower = min(float(running.min()), 0.0)
    upper = max(float(running.max()), 0.0)
    span = max(upper - lower, 0.2)
    barcode_bottom = lower - 0.23 * span
    barcode_top = lower - 0.10 * span
    axis.plot(ranks, running, color=color, linewidth=1.8)
    axis.fill_between(ranks, 0, running, color=color, alpha=0.13)
    axis.axhline(0, color="#6F7B79", linewidth=0.8)
    axis.axvline(peak, color=color, linewidth=0.9, linestyle=(0, (2, 2)), alpha=0.8)
    axis.vlines(hits, barcode_bottom, barcode_top, color=color, linewidth=0.42, alpha=0.75)
    axis.set_xlim(1, len(running))
    axis.set_ylim(barcode_bottom - 0.04 * span, upper + 0.19 * span)
    axis.set_title(title, loc="left", fontsize=11.5, fontweight="bold", color="#172322", pad=7)
    axis.text(0.99, 0.96, f"ES = {score:+.3f}\n{mapped}/200 genes mapped", transform=axis.transAxes, ha="right", va="top", fontsize=9.3, color=color, linespacing=1.35)
    axis.text(0.01, 1.08, panel, transform=axis.transAxes, ha="left", va="bottom", fontsize=15, fontweight="bold", color="#111817")
    axis.text(1 + 0.01 * len(running), barcode_top + 0.035 * span, "Gene-set hits", ha="left", va="bottom", fontsize=8.6, color="#62706E")
    axis.set_xlabel("Ranked genes: KRAS siRNA vs nonspecific siRNA log2FC", fontsize=9.6)
    axis.set_ylabel("Running ES", fontsize=9.6)
    axis.tick_params(labelsize=9)
    style_axis(axis)


base = Path(__file__).resolve().parent
data_path = find_input(base, "science.adk0775_data_s1.csv")
gmt_path = find_input(base, "h.all.v2023.2.Hs.symbols.gmt")
output_path = base / "kras_volcano_preranked_gsea.png"
required = {"external_gene_name", "logFC", "FDR"}
data = pd.read_csv(data_path)
if not required.issubset(data.columns):
    raise ValueError(f"CSV must contain columns: {sorted(required)}")
data["logFC"] = pd.to_numeric(data["logFC"], errors="coerce")
data["FDR"] = pd.to_numeric(data["FDR"], errors="coerce")
plot_data = data.loc[np.isfinite(data["logFC"]) & np.isfinite(data["FDR"]) & (data["FDR"] > 0)].copy()
plot_data["external_gene_name"] = plot_data["external_gene_name"].astype("string")
valid = plot_data.loc[plot_data["external_gene_name"].notna() & (plot_data["external_gene_name"].str.strip() != "")].copy()
valid["external_gene_name"] = valid["external_gene_name"].str.strip()
valid["_source_order"] = np.arange(len(valid))
valid["_abs_logfc"] = valid["logFC"].abs()
collapsed = valid.sort_values(
    ["external_gene_name", "_abs_logfc", "FDR", "_source_order"],
    ascending=[True, False, True, True],
    kind="mergesort",
).drop_duplicates("external_gene_name", keep="first")
ranked = collapsed.sort_values(
    ["logFC", "_source_order"],
    ascending=[False, True],
    kind="mergesort",
).reset_index(drop=True)
set_names = ("HALLMARK_KRAS_SIGNALING_UP", "HALLMARK_KRAS_SIGNALING_DN")
gene_sets = read_gmt(gmt_path, set_names)
up_curve = enrichment_curve(ranked, gene_sets[set_names[0]])
dn_curve = enrichment_curve(ranked, gene_sets[set_names[1]])
plot_data["neglog10_fdr"] = -np.log10(plot_data["FDR"])
up_sig = (plot_data["FDR"] < 0.05) & (plot_data["logFC"] > 0.5)
down_sig = (plot_data["FDR"] < 0.05) & (plot_data["logFC"] < -0.5)
symbol_values = plot_data["external_gene_name"].fillna("").astype(str)
up_members = symbol_values.isin(gene_sets[set_names[0]])
dn_members = symbol_values.isin(gene_sets[set_names[1]])
special = symbol_values.isin({"KRAS", "FOSL1", "MYC"})
x_extent = math.ceil(max(abs(float(plot_data["logFC"].min())), abs(float(plot_data["logFC"].max()))) * 2) / 2
y_extent = max(6.5, float(plot_data["neglog10_fdr"].max()) + 0.45)
threshold_y = -math.log10(0.05)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9.5, "axes.linewidth": 0.85, "figure.facecolor": "#F7F6F2", "axes.facecolor": "#F7F6F2", "savefig.facecolor": "#F7F6F2"})
figure = plt.figure(figsize=(12.0, 8.6))
grid = figure.add_gridspec(2, 2, width_ratios=(1.58, 1.0), height_ratios=(1, 1), left=0.075, right=0.975, top=0.84, bottom=0.21, wspace=0.34, hspace=0.44)
volcano = figure.add_subplot(grid[:, 0])
volcano.add_patch(Rectangle((-x_extent, threshold_y), x_extent - 0.5, y_extent - threshold_y, facecolor="#426EAA", alpha=0.055, linewidth=0))
volcano.add_patch(Rectangle((0.5, threshold_y), x_extent - 0.5, y_extent - threshold_y, facecolor="#D65A4A", alpha=0.055, linewidth=0))
volcano.scatter(plot_data["logFC"], plot_data["neglog10_fdr"], s=7.5, c="#B8BFBC", alpha=0.30, linewidths=0, rasterized=True)
volcano.scatter(plot_data.loc[down_sig, "logFC"], plot_data.loc[down_sig, "neglog10_fdr"], s=9, c="#426EAA", alpha=0.40, linewidths=0, rasterized=True)
volcano.scatter(plot_data.loc[up_sig, "logFC"], plot_data.loc[up_sig, "neglog10_fdr"], s=9, c="#D65A4A", alpha=0.40, linewidths=0, rasterized=True)
volcano.scatter(plot_data.loc[up_members, "logFC"], plot_data.loc[up_members, "neglog10_fdr"], s=24, facecolors="#E7A621", edgecolors="#172322", linewidths=0.38, alpha=0.88, zorder=4)
volcano.scatter(plot_data.loc[dn_members, "logFC"], plot_data.loc[dn_members, "neglog10_fdr"], s=22, facecolors="#8EA4C9", edgecolors="#172322", linewidths=0.38, alpha=0.86, zorder=4)
volcano.scatter(plot_data.loc[special, "logFC"], plot_data.loc[special, "neglog10_fdr"], s=48, facecolors="#46C8C8", edgecolors="#142020", linewidths=0.75, zorder=6)
volcano.axvline(-0.5, color="#426EAA", linewidth=0.9, linestyle=(0, (2, 2)))
volcano.axvline(0.5, color="#D65A4A", linewidth=0.9, linestyle=(0, (2, 2)))
volcano.axhline(threshold_y, color="#596664", linewidth=0.9, linestyle=(0, (2, 2)))
volcano.axvline(0, color="#899390", linewidth=0.75)
for gene, offset in {"KRAS": (10, 5), "FOSL1": (10, 9), "MYC": (10, 8)}.items():
    rows = plot_data.loc[symbol_values == gene]
    if not rows.empty:
        row = rows.iloc[0]
        volcano.annotate(gene, (row["logFC"], row["neglog10_fdr"]), xytext=offset, textcoords="offset points", fontsize=9, fontweight="bold", color="#172322", bbox={"boxstyle": "round,pad=0.22", "facecolor": "#F7F6F2", "edgecolor": "#6D7977", "linewidth": 0.65}, arrowprops={"arrowstyle": "-", "color": "#6D7977", "linewidth": 0.65})
volcano.text(-0.075, 1.035, "A", transform=volcano.transAxes, fontsize=15, fontweight="bold", ha="left", va="bottom", clip_on=False)
volcano.set_title("KRAS suppression reshapes the PDAC transcriptome", loc="left", fontsize=14.2, fontweight="bold", color="#172322", pad=15)
volcano.text(0.02, 0.98, f"{int(down_sig.sum()):,} KRAS-dependent genes", transform=volcano.transAxes, color="#426EAA", fontsize=9.6, fontweight="bold", va="top")
volcano.text(0.98, 0.98, f"{int(up_sig.sum()):,} KRAS-inhibited genes", transform=volcano.transAxes, color="#D65A4A", fontsize=9.6, fontweight="bold", ha="right", va="top")
volcano.text(0.985, threshold_y / y_extent + 0.015, "FDR = 0.05", transform=volcano.transAxes, ha="right", va="bottom", fontsize=8.8, color="#596664")
volcano.set_xlim(-x_extent, x_extent)
volcano.set_ylim(0, y_extent)
volcano.set_xlabel("KRAS siRNA vs nonspecific siRNA log2FC", fontsize=11.2)
volcano.set_ylabel("Significance (-log10 FDR)", fontsize=11.2)
volcano.tick_params(labelsize=9.6)
style_axis(volcano)
legend_items = [
    Line2D([0], [0], marker="o", linestyle="", markerfacecolor="#426EAA", markeredgecolor="none", markersize=5.5, label="FDR < 0.05, log2FC < -0.5"),
    Line2D([0], [0], marker="o", linestyle="", markerfacecolor="#D65A4A", markeredgecolor="none", markersize=5.5, label="FDR < 0.05, log2FC > 0.5"),
    Line2D([0], [0], marker="o", linestyle="", markerfacecolor="#E7A621", markeredgecolor="#172322", markeredgewidth=0.4, markersize=6, label="HALLMARK KRAS SIGNALING UP"),
    Line2D([0], [0], marker="o", linestyle="", markerfacecolor="#8EA4C9", markeredgecolor="#172322", markeredgewidth=0.4, markersize=6, label="HALLMARK KRAS SIGNALING DN")
]
figure.legend(handles=legend_items, loc="lower left", bbox_to_anchor=(0.075, 0.100), ncol=2, frameon=False, fontsize=8.4, handletextpad=0.45, columnspacing=1.2)
up_axis = figure.add_subplot(grid[0, 1])
dn_axis = figure.add_subplot(grid[1, 1])
draw_enrichment(up_axis, *up_curve, "HALLMARK KRAS SIGNALING UP", "#D99716", "B")
draw_enrichment(dn_axis, *dn_curve, "HALLMARK KRAS SIGNALING DN", "#647FAE", "C")
figure.suptitle("Differential expression and Hallmark KRAS preranked enrichment", x=0.075, y=0.965, ha="left", fontsize=17.5, fontweight="bold", color="#13201F")
figure.text(0.075, 0.047, "Weighted preranked ES (|log2FC|¹); duplicate symbols retain max |log2FC|, then min FDR, then source order. Gene sets: MSigDB Hallmark v2023.2.", ha="left", va="bottom", fontsize=8.9, color="#485654")
figure.text(0.075, 0.022, "Only gene-level summaries are supplied: phenotype-permutation P is not estimable, and this self-contained ES-only analysis reports neither permutation P nor NES.", ha="left", va="bottom", fontsize=8.9, color="#485654")
figure.savefig(output_path, dpi=400)
plt.close(figure)
print(f"Rows: {len(data):,}; ranked unique symbols: {len(ranked):,}")
print(f"DEG threshold counts: down={int(down_sig.sum()):,}, up={int(up_sig.sum()):,}")
print(f"{set_names[0]}: ES={up_curve[2]:.10f}, mapped={up_curve[4]}/200")
print(f"{set_names[1]}: ES={dn_curve[2]:.10f}, mapped={dn_curve[4]}/200")
print(output_path)
