from pathlib import Path
import csv
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle


BASE = Path(__file__).resolve().parent
CLUSTER_COLORS = {1: "#1f77b4", 2: "#ff7f0e", 3: "#2ca02c", 4: "#d62728", 5: "#9467bd", 6: "#8c564b", 7: "#e377c2", 8: "#7f7f7f", 9: "#bcbd22"}
HEATMAP = LinearSegmentedColormap.from_list("expression", ["#164e8a", "#f7f5f2", "#b3202a"])


def read_matrix(filename):
    with (BASE / filename).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        rows = list(reader)
    genes = [row[0] for row in rows]
    values = np.array([[float(value) for value in row[1:]] for row in rows], dtype=float)
    if len(genes) != len(set(genes)) or not np.isfinite(values).all():
        raise ValueError(f"Invalid matrix in {filename}")
    return genes, header[1:], values


def read_assignments():
    result = {"embryonic": [], "pbmc": []}
    with (BASE / "gene_cluster_assignments.csv").open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            result[row["dataset"]].append((row["gene"], int(row["cluster"]), float(row["score"])))
    return result


def read_enrichment():
    result = {"embryonic": {}, "pbmc": {}}
    with (BASE / "enrichment_annotations.csv").open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            dataset = row["dataset"]
            cluster = int(row["cluster"])
            result[dataset].setdefault(cluster, []).append((int(row["rank"]), row["term"], float(row["relative_score"])))
    for dataset in result:
        for cluster in result[dataset]:
            result[dataset][cluster].sort(key=lambda item: item[0])
    return result


def row_zscore(values):
    centered = values - values.mean(axis=1, keepdims=True)
    spread = values.std(axis=1, ddof=1, keepdims=True)
    spread[spread == 0] = 1
    return centered / spread


def stable_profile_order(values):
    if len(values) < 3:
        return np.arange(len(values))
    centered = values - values.mean(axis=0, keepdims=True)
    _, _, vectors = np.linalg.svd(centered, full_matrices=False)
    direction = vectors[0]
    first = np.flatnonzero(np.abs(direction) > 1e-12)
    if len(first) and direction[first[0]] < 0:
        direction = -direction
    projection = np.sum(centered * direction[None, :], axis=1)
    return np.argsort(projection, kind="stable")


def prepare_embryonic(assignments):
    genes, samples, expression = read_matrix("embryonic_expression.csv")
    if expression.shape != (3767, 6):
        raise ValueError("Embryonic expression matrix must contain 3,767 genes and 6 stages")
    assignment = {gene: (cluster, score) for gene, cluster, score in assignments}
    if set(assignment) != set(genes):
        raise ValueError("Embryonic cluster assignments do not match the expression matrix")
    clusters = np.array([assignment[gene][0] for gene in genes], dtype=int)
    scores = np.array([assignment[gene][1] for gene in genes], dtype=float)
    expected = {1: 372, 2: 281, 3: 282, 4: 847, 5: 250, 6: 424, 7: 961, 8: 350}
    observed = {cluster: int((clusters == cluster).sum()) for cluster in expected}
    if observed != expected:
        raise ValueError(f"Unexpected embryonic cluster sizes: {observed}")
    labels = ["Zygote", "2-cell", "4-cell", "8-cell", "Morula", "Blastocyst"]
    colors = ["#f1d94f", "#7776de", "#d67812", "#75dca2", "#f27418", "#1768b5"]
    representatives = {1: ["Apeh", "Ckb", "Nit2"], 2: ["Abcf1", "Top2a", "Ipo5"], 3: ["Fam192a", "Ndufb11"], 4: ["Fem1b", "Thrap3", "Peci", "Psmd11"], 5: ["Tbc1d23", "Dusp7", "Cdk5rap2"], 6: ["Rab27a", "Dtx2", "Acad10", "AU015836"], 7: ["Morc3", "Yipf3", "Luc7l2", "Timm8a1"], 8: ["Tbcc", "Atp11c", "Tm7sf2", "LOC100503972"]}
    return genes, labels, row_zscore(expression), clusters, scores, [6, 1, 8, 5, 3, 7, 4, 2], colors, representatives


def prepare_pbmc(assignments):
    genes, cells, expression = read_matrix("pbmc_normalized_expression.csv")
    if expression.shape != (500, 500):
        raise ValueError("PBMC expression matrix must contain 500 genes and 500 cells")
    with (BASE / "pbmc_cell_metadata.csv").open(newline="", encoding="utf-8-sig") as handle:
        metadata = {row["cell"]: row["cell_type"] for row in csv.DictReader(handle)}
    levels = ["Naive CD4 T", "Memory CD4 T", "CD14+ Mono", "B", "CD8 T", "FCGR3A+ Mono", "NK", "DC", "Platelet"]
    labels = np.array([metadata[cell] for cell in cells])
    if set(labels) != set(levels):
        raise ValueError("PBMC cell annotations are incomplete")
    marker_genes = [item[0] for item in assignments]
    index = {gene: position for position, gene in enumerate(genes)}
    if len(marker_genes) != 77 or any(gene not in index for gene in marker_genes):
        raise ValueError("PBMC marker assignments are incomplete")
    linear = np.expm1(expression)
    average = np.column_stack([linear[:, labels == level].mean(axis=1) for level in levels])
    selected = average[[index[gene] for gene in marker_genes]]
    clusters = np.array([item[1] for item in assignments], dtype=int)
    scores = np.array([item[2] for item in assignments], dtype=float)
    expected = [6, 6, 15, 5, 4, 12, 6, 18, 5]
    observed = [int((clusters == cluster).sum()) for cluster in range(1, 10)]
    if observed != expected:
        raise ValueError(f"Unexpected PBMC marker cluster sizes: {observed}")
    colors = ["#7a9a01", "#4de88d", "#62e679", "#3a12c6", "#84aaa0", "#d000b9", "#168ca8", "#71dedc", "#58efb5"]
    representatives = {1: ["RPS23", "FUS", "RPSA"], 2: ["GIMAP7", "CRIP1", "PRDX2"], 3: ["GPX1", "JUND", "LYL1", "VAMP5"], 4: ["PKIG", "POLD4", "SELL"], 5: ["SH2D1A", "BIN2", "CELF2"], 6: ["MBD2", "CXCL16", "TMEM127", "RAB31"], 7: ["C19orf10", "MAD2L2", "TMBIM4.1", "CARD8"], 8: ["TRAPPC9", "AMPD2", "ENHO", "PRR14L"], 9: ["CD9", "RBBP6", "GNG11"]}
    return marker_genes, levels, row_zscore(selected), clusters, scores, list(range(1, 10)), colors, representatives


def render_figure(dataset, genes, samples, values, clusters, scores, cluster_order, sample_colors, representatives, enrichment, title, subtitle, output):
    order = []
    blocks = []
    start = 0
    for cluster in cluster_order:
        positions = np.where(clusters == cluster)[0]
        local = stable_profile_order(values[positions]) if dataset == "embryonic" else np.arange(len(positions))
        positions = positions[local]
        order.extend(positions.tolist())
        end = start + len(positions)
        blocks.append((cluster, start, end, len(positions)))
        start = end
    order = np.array(order, dtype=int)
    displayed_values = values[order]
    displayed_genes = [genes[index] for index in order]
    displayed_clusters = clusters[order]
    displayed_scores = scores[order]
    total = len(displayed_genes)
    figure = plt.figure(figsize=(20, 12), facecolor="white")
    grid = figure.add_gridspec(1, 6, width_ratios=[1.7, 1.55, 1.6, 0.22, 5.6, 1.55], left=0.045, right=0.965, bottom=0.075, top=0.84, wspace=0.035)
    profile_axis = figure.add_subplot(grid[0, 0])
    gene_axis = figure.add_subplot(grid[0, 1], sharey=profile_axis)
    heat_axis = figure.add_subplot(grid[0, 2], sharey=profile_axis)
    stripe_axis = figure.add_subplot(grid[0, 3], sharey=profile_axis)
    term_axis = figure.add_subplot(grid[0, 4], sharey=profile_axis)
    bar_axis = figure.add_subplot(grid[0, 5], sharey=profile_axis)
    image = heat_axis.imshow(displayed_values, aspect="auto", interpolation="nearest", cmap=HEATMAP, vmin=-2, vmax=2, extent=(-0.5, len(samples) - 0.5, total, 0), rasterized=True)
    heat_axis.set_xlim(-0.5, len(samples) - 0.5)
    heat_axis.set_ylim(total, 0)
    heat_axis.set_yticks([])
    heat_axis.set_xticks(np.arange(len(samples)))
    heat_axis.set_xticklabels(samples, rotation=40, ha="left", va="bottom", fontsize=9.2)
    heat_axis.tick_params(axis="x", top=True, labeltop=True, bottom=False, labelbottom=False, length=0, pad=20)
    for position, color in enumerate(sample_colors):
        heat_axis.add_patch(Rectangle((position - 0.5, -total * 0.024), 1, total * 0.016, transform=heat_axis.transData, facecolor=color, edgecolor="white", linewidth=0.7, clip_on=False))
    for spine in heat_axis.spines.values():
        spine.set_color("#26323d")
        spine.set_linewidth(0.9)
    for axis in [profile_axis, gene_axis, stripe_axis, term_axis, bar_axis]:
        axis.set_ylim(total, 0)
        axis.set_yticks([])
    profile_axis.set_xlim(-0.38, 1.04)
    gene_axis.set_xlim(0, 1)
    stripe_axis.set_xlim(0, 1)
    term_axis.set_xlim(0, 1)
    bar_axis.set_xlim(0, 1.04)
    for axis in [profile_axis, gene_axis, stripe_axis, term_axis, bar_axis]:
        axis.set_xticks([])
        for spine in axis.spines.values():
            spine.set_visible(False)
    profile_axis.text(0.38, 1.035, "Cluster profile", transform=profile_axis.transAxes, ha="center", va="bottom", fontsize=10.5, fontweight="bold", color="#26323d")
    gene_axis.text(0.95, 1.035, "Representative genes", transform=gene_axis.transAxes, ha="right", va="bottom", fontsize=10.5, fontweight="bold", color="#26323d")
    term_axis.text(0.02, 1.035, "Functional enrichment", transform=term_axis.transAxes, ha="left", va="bottom", fontsize=10.5, fontweight="bold", color="#26323d")
    bar_axis.text(0.5, 1.035, "Relative enrichment", transform=bar_axis.transAxes, ha="center", va="bottom", fontsize=10.5, fontweight="bold", color="#26323d")
    gene_position = {gene: position + 0.5 for position, gene in enumerate(displayed_genes)}
    sample_x = np.linspace(0.02, 0.98, len(samples))
    for block_number, (cluster, block_start, block_end, count) in enumerate(blocks):
        height = block_end - block_start
        center = (block_start + block_end) / 2
        color = CLUSTER_COLORS[cluster]
        profile_axis.add_patch(Rectangle((-0.06, block_start), 1.08, height, facecolor="#f6f7f8" if block_number % 2 == 0 else "#ffffff", edgecolor="#d8dde2", linewidth=0.8))
        block_values = displayed_values[displayed_clusters == cluster]
        median = np.median(block_values, axis=0)
        amplitude = max(float(np.max(np.abs(median))), 0.5)
        profile_y = center - median / amplitude * height * 0.28
        profile_axis.plot(sample_x, profile_y, color="white", linewidth=4.2, solid_capstyle="round", zorder=2)
        profile_axis.plot(sample_x, profile_y, color=color, linewidth=2.4, solid_capstyle="round", zorder=3)
        profile_axis.text(-0.34, center, f"C{cluster}", ha="left", va="center", fontsize=11.5, fontweight="bold", color="#26323d")
        profile_axis.text(-0.02, block_start + height * 0.12, f"n = {count}", ha="left", va="top", fontsize=7.8, color="#5e6a74")
        candidates = [gene for gene in representatives.get(cluster, []) if gene in gene_position and displayed_clusters[int(gene_position[gene] - 0.5)] == cluster]
        if candidates:
            label_y = np.linspace(block_start + height * 0.16, block_end - height * 0.16, len(candidates))
            for gene, target_y in zip(candidates, label_y):
                actual_y = gene_position[gene]
                gene_axis.plot([0.88, 1], [target_y, actual_y], color="#8b949c", linewidth=0.75, clip_on=False)
                gene_axis.text(0.84, target_y, gene, ha="right", va="center", fontsize=7.9 if dataset == "embryonic" else 8.6, fontstyle="italic", color="#26323d")
        stripe_axis.add_patch(Rectangle((0, block_start), 1, height, facecolor=color, edgecolor="white", linewidth=1.1))
        stripe_axis.text(0.5, center, f"C{cluster}  n={count}", rotation=90, ha="center", va="center", fontsize=7.2, fontweight="bold", color="white")
        term_axis.add_patch(Rectangle((0, block_start), 1, height, facecolor="#f7f7f6" if block_number % 2 == 0 else "#fbfbfa", edgecolor="#aeb6bc", linewidth=0.8))
        terms = enrichment[cluster]
        if dataset == "pbmc" and height <= 5:
            terms = terms[:3]
        term_y = np.linspace(block_start + height * 0.14, block_end - height * 0.14, len(terms))
        font_size = 8.0 if dataset == "pbmc" else 8.7
        for term_index, ((rank, term, relative_score), y_value) in enumerate(zip(terms, term_y)):
            term_axis.text(0.025, y_value, term, ha="left", va="center", fontsize=font_size + (0.8 if term_index == 0 else 0), fontweight="bold" if term_index == 0 else "normal", color=color, clip_on=True)
            bar_height = max(total * 0.0015, height / (len(terms) * 2.8))
            bar_axis.barh(y_value, 1, height=bar_height, color="#eef0f2", edgecolor="none")
            bar_axis.barh(y_value, relative_score, height=bar_height, color=color, edgecolor="none")
        for axis in [gene_axis, heat_axis, stripe_axis, bar_axis]:
            axis.axhline(block_end, color="#d4d9dd", linewidth=0.65, zorder=4)
    figure.text(0.045, 0.958, title, ha="left", va="top", fontsize=23, fontweight="bold", color="#202a33")
    figure.text(0.045, 0.922, subtitle, ha="left", va="top", fontsize=11.5, color="#687680")
    figure.text(0.045, 0.032, "Rows are genes; colors show row-wise z-scores. Profiles summarize median expression within each cluster.", ha="left", va="center", fontsize=8.8, color="#687680")
    color_axis = figure.add_axes([0.82, 0.026, 0.13, 0.014])
    colorbar = figure.colorbar(image, cax=color_axis, orientation="horizontal", ticks=[-2, 0, 2])
    colorbar.ax.tick_params(labelsize=7.8, length=2, colors="#49545d", pad=1)
    colorbar.outline.set_visible(False)
    colorbar.ax.set_title("Row z-score", fontsize=8.2, color="#49545d", pad=3)
    figure.savefig(BASE / output, dpi=220, facecolor="white", edgecolor="none")
    plt.close(figure)


def main():
    plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"], "axes.unicode_minus": False, "savefig.facecolor": "white"})
    assignments = read_assignments()
    enrichment = read_enrichment()
    embryo = prepare_embryonic(assignments["embryonic"])
    render_figure("embryonic", *embryo, enrichment["embryonic"], "Embryonic expression programs", "Fuzzy clustering of 3,767 genes across six stages of preimplantation development", "embryonic_gene_cluster_heatmap.png")
    pbmc = prepare_pbmc(assignments["pbmc"])
    render_figure("pbmc", *pbmc, enrichment["pbmc"], "Cell-type marker programs", "Differential expression and functional enrichment across nine PBMC lineages", "pbmc_gene_cluster_heatmap.png")


if __name__ == "__main__":
    main()
