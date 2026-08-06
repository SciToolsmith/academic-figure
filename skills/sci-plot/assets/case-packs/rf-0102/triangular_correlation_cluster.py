from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch
from scipy.cluster.hierarchy import dendrogram, leaves_list, linkage
from scipy.spatial.distance import squareform


def resolve_input(script_dir, filename):
    candidates = (script_dir / "data" / filename, script_dir / filename)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Input file not found: {filename}")


def load_inputs(script_dir):
    data_path = resolve_input(script_dir, "data.csv")
    group_path = resolve_input(script_dir, "group.csv")
    data = pd.read_csv(data_path, index_col=0)
    groups = pd.read_csv(group_path, dtype=str, keep_default_na=False)
    if data.shape[0] < 3 or data.shape[1] < 2:
        raise ValueError("data.csv must contain at least three observations and two variables")
    if data.index.has_duplicates or data.columns.has_duplicates:
        raise ValueError("Observation identifiers and variable names must be unique")
    if list(groups.columns) != ["Bile acid", "order"]:
        raise ValueError("group.csv must contain the columns 'Bile acid' and 'order'")
    if groups["Bile acid"].duplicated().any():
        raise ValueError("Every variable must occur exactly once in group.csv")
    if set(groups["Bile acid"]) != set(data.columns):
        missing = sorted(set(data.columns) - set(groups["Bile acid"]))
        extra = sorted(set(groups["Bile acid"]) - set(data.columns))
        raise ValueError(f"Variable/group mismatch; missing={missing}, extra={extra}")
    numeric = data.apply(pd.to_numeric, errors="raise")
    values = numeric.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("data.csv contains non-finite values")
    if np.any(values < 0):
        raise ValueError("Log transformation requires non-negative measurements")
    return numeric, groups


def calculate_structure(data):
    values = data.to_numpy(dtype=float)
    positives = values[values > 0]
    if positives.size == 0:
        raise ValueError("At least one positive measurement is required")
    minimum_positive = float(positives.min())
    pseudocount = minimum_positive / 2.0
    if not np.isclose(pseudocount, 0.005, rtol=0, atol=1e-12):
        raise ValueError(
            f"Expected a minimum positive value of 0.01, observed {minimum_positive:g}"
        )
    transformed = np.log10(values + pseudocount)
    standard_deviation = transformed.std(axis=0, ddof=1)
    if np.any(standard_deviation == 0):
        constant = data.columns[standard_deviation == 0].tolist()
        raise ValueError(f"Correlation is undefined for constant variables: {constant}")
    correlation = np.corrcoef(transformed, rowvar=False)
    if not np.isfinite(correlation).all():
        raise ValueError("Correlation matrix contains non-finite values")
    if not np.allclose(correlation, correlation.T, atol=1e-12):
        raise ValueError("Correlation matrix is not symmetric")
    distance_component = 1.0 - correlation
    if distance_component.min() < -1e-10 or distance_component.max() > 2.0 + 1e-10:
        raise ValueError("Correlation-derived distance is outside its valid range")
    distance_component = np.maximum(distance_component, 0.0)
    chord_distance = np.sqrt(2.0 * distance_component)
    chord_distance = (chord_distance + chord_distance.T) / 2.0
    np.fill_diagonal(chord_distance, 0.0)
    hierarchy = linkage(
        squareform(chord_distance, checks=True),
        method="average",
        optimal_ordering=False,
    )
    n_variables = correlation.shape[0]
    minimum_leaf = np.empty(2 * n_variables - 1, dtype=int)
    minimum_leaf[:n_variables] = np.arange(n_variables)
    for merge_index in range(n_variables - 1):
        left = int(hierarchy[merge_index, 0])
        right = int(hierarchy[merge_index, 1])
        if minimum_leaf[left] > minimum_leaf[right]:
            hierarchy[merge_index, 0], hierarchy[merge_index, 1] = (
                hierarchy[merge_index, 1],
                hierarchy[merge_index, 0],
            )
            left, right = right, left
        minimum_leaf[n_variables + merge_index] = min(
            minimum_leaf[left], minimum_leaf[right]
        )
    order = leaves_list(hierarchy)
    ordered = correlation[np.ix_(order, order)]
    if not np.allclose(np.diag(ordered), 1.0, atol=1e-10):
        raise ValueError("Correlation diagonal validation failed")
    return pseudocount, correlation, hierarchy, order, ordered


def build_figure(data, groups, pseudocount, hierarchy, order, ordered):
    mpl.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8,
            "axes.titlesize": 10,
            "axes.labelsize": 8,
            "axes.linewidth": 0.7,
            "xtick.major.width": 0.6,
            "ytick.major.width": 0.6,
            "savefig.facecolor": "white",
        }
    )
    names = data.columns.to_numpy()[order]
    group_lookup = groups.set_index("Bile acid")["order"]
    group_labels = {
        "priConjSum": "Primary conjugated",
        "primarySum": "Primary unconjugated",
        "secConjSum": "Secondary conjugated",
        "secondarySum": "Secondary unconjugated",
        "": "Unassigned",
    }
    group_colors = {
        "Primary conjugated": "#2A9D8F",
        "Primary unconjugated": "#E9C46A",
        "Secondary conjugated": "#457B9D",
        "Secondary unconjugated": "#E76F51",
        "Unassigned": "#B5B7BA",
    }
    unknown_codes = sorted(set(group_lookup) - set(group_labels))
    if unknown_codes:
        raise ValueError(f"Unknown group codes: {unknown_codes}")
    ordered_groups = [group_labels[group_lookup[name]] for name in names]
    group_rgba = np.array(
        [[mpl.colors.to_rgba(group_colors[label]) for label in ordered_groups]]
    )
    n_variables = len(names)
    extent = (0, n_variables * 10, n_variables * 10, 0)
    figure = plt.figure(figsize=(16, 14), constrained_layout=False)
    grid = figure.add_gridspec(
        3,
        2,
        width_ratios=(1, 0.035),
        height_ratios=(2.0, 0.28, 8.5),
        left=0.20,
        right=0.90,
        bottom=0.23,
        top=0.88,
        hspace=0.03,
        wspace=0.05,
    )
    dendrogram_axis = figure.add_subplot(grid[0, 0])
    group_axis = figure.add_subplot(grid[1, 0])
    heat_axis = figure.add_subplot(grid[2, 0])
    color_axis = figure.add_subplot(grid[2, 1])
    dendrogram(
        hierarchy,
        ax=dendrogram_axis,
        no_labels=True,
        color_threshold=0,
        above_threshold_color="#344E41",
        link_color_func=lambda _: "#344E41",
    )
    for collection in dendrogram_axis.collections:
        collection.set_linewidth(0.75)
    dendrogram_axis.set_xlim(0, n_variables * 10)
    dendrogram_axis.set_ylabel("Chord distance", color="#33413B")
    dendrogram_axis.set_xticks([])
    dendrogram_axis.tick_params(axis="y", labelsize=7, colors="#52625B")
    dendrogram_axis.spines[["top", "right", "bottom"]].set_visible(False)
    dendrogram_axis.spines["left"].set_color("#AEB7B2")
    group_axis.imshow(group_rgba, aspect="auto", extent=extent)
    group_axis.set_xlim(0, n_variables * 10)
    group_axis.set_ylim(10, 0)
    group_axis.set_xticks([])
    group_axis.set_yticks([])
    for spine in group_axis.spines.values():
        spine.set_visible(False)
    palette = LinearSegmentedColormap.from_list(
        "correlation",
        ["#254E70", "#79A9C7", "#F7F5F0", "#E49773", "#9D2A32"],
        N=256,
    )
    masked = np.ma.masked_where(
        np.triu(np.ones_like(ordered, dtype=bool), k=1), ordered
    )
    image = heat_axis.imshow(
        masked,
        cmap=palette,
        vmin=-1,
        vmax=1,
        interpolation="nearest",
        aspect="equal",
        extent=extent,
    )
    centers = np.arange(n_variables) * 10 + 5
    heat_axis.set_xticks(centers)
    heat_axis.set_yticks(centers)
    heat_axis.set_xticklabels(
        names,
        rotation=58,
        ha="right",
        va="top",
        rotation_mode="anchor",
        fontsize=5.8,
        color="#26332D",
    )
    heat_axis.set_yticklabels(names, fontsize=5.8, color="#26332D")
    heat_axis.tick_params(axis="both", length=2.5, color="#89958F", pad=2)
    heat_axis.set_xlim(0, n_variables * 10)
    heat_axis.set_ylim(n_variables * 10, 0)
    heat_axis.spines[["top", "right"]].set_visible(False)
    heat_axis.spines[["left", "bottom"]].set_color("#AEB7B2")
    heat_axis.plot(
        [0, n_variables * 10],
        [0, n_variables * 10],
        color="#FFFFFF",
        linewidth=0.5,
        alpha=0.8,
    )
    colorbar = figure.colorbar(image, cax=color_axis, ticks=[-1, -0.5, 0, 0.5, 1])
    colorbar.set_label("Pearson correlation (r)", labelpad=8)
    colorbar.ax.tick_params(labelsize=7, length=2)
    colorbar.outline.set_linewidth(0.6)
    figure.text(
        0.20,
        0.955,
        "Bile acid correlation structure",
        fontsize=22,
        fontweight="bold",
        color="#17251F",
        ha="left",
        va="top",
    )
    figure.text(
        0.20,
        0.922,
        "Lower-triangular correlation matrix with hierarchical clustering",
        fontsize=11,
        color="#52625B",
        ha="left",
        va="top",
    )
    figure.text(
        0.20,
        0.895,
        (
            f"n = {data.shape[0]} observations · Pearson r on log10(x + "
            f"{pseudocount:.3f}) · chord distance √[2(1 − r)] · average linkage"
        ),
        fontsize=8.5,
        color="#68766F",
        ha="left",
        va="top",
    )
    legend_order = [
        "Primary conjugated",
        "Primary unconjugated",
        "Secondary conjugated",
        "Secondary unconjugated",
        "Unassigned",
    ]
    handles = [
        Patch(facecolor=group_colors[label], edgecolor="none", label=label)
        for label in legend_order
    ]
    figure.legend(
        handles=handles,
        loc="upper right",
        bbox_to_anchor=(0.90, 0.925),
        ncol=1,
        frameon=False,
        title="Bile acid class",
        title_fontsize=8,
        fontsize=7.5,
        handlelength=1.4,
        handleheight=0.8,
        labelspacing=0.45,
    )
    figure.text(
        0.20,
        0.06,
        (
            "The 0.005 pseudocount equals half the smallest positive observation (0.01). "
            "The colored strip reports the supplied group annotation. "
            "Variables without a supplied class are shown as Unassigned."
        ),
        fontsize=7.5,
        color="#68766F",
        ha="left",
        va="bottom",
    )
    return figure


def main():
    script_dir = Path(__file__).resolve().parent
    output_path = script_dir / "triangular_correlation_cluster.png"
    data, groups = load_inputs(script_dir)
    pseudocount, correlation, hierarchy, order, ordered = calculate_structure(data)
    figure = build_figure(data, groups, pseudocount, hierarchy, order, ordered)
    figure.savefig(output_path, dpi=300, bbox_inches=None, facecolor="white")
    plt.close(figure)
    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise OSError(f"Figure was not written: {output_path}")
    unassigned = int((groups["order"] == "").sum())
    print(
        f"Saved: {output_path}\n"
        f"Observations: {data.shape[0]}; variables: {data.shape[1]}; "
        f"unassigned groups: {unassigned}; pseudocount: {pseudocount:.3f}; "
        f"correlation range: [{correlation.min():.3f}, {correlation.max():.3f}]"
    )


if __name__ == "__main__":
    main()
