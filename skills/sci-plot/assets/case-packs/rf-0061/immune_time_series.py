from pathlib import Path
import csv
import math
import textwrap

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import to_rgb
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import MaxNLocator, PercentFormatter
from scipy.ndimage import gaussian_filter1d
from scipy.stats import gaussian_kde, spearmanr, t


BASE_DIR = Path(__file__).resolve().parent
PROFILE_DATA = BASE_DIR / "immune_age_profiles.xlsx"
LONGITUDINAL_DATA = BASE_DIR / "longitudinal_immune_dynamics.xlsx"
COLOR_DATA = BASE_DIR / "cell_type_colors.csv"
STREAM_OUTPUTS = {
    "CD8 T cells": BASE_DIR / "cd8_t_cell_streamgraph.png",
    "CD4 T cells": BASE_DIR / "cd4_t_cell_streamgraph.png",
    "B cells": BASE_DIR / "b_cell_streamgraph.png",
}
LONGITUDINAL_OUTPUT = BASE_DIR / "longitudinal_cell_dynamics.png"
CURVE_OUTPUT = BASE_DIR / "rna_age_metric_curves.png"
AGE_GROUP_COLORS = {"Young": "#35978F", "Older": "#BF812D"}
STREAM_GROUPS = {
    "CD8 T cells": [
        "KLRF1+ GZMB+ CD27- EM CD8 T cell",
        "KLRF1- GZMB+ CD27- EM CD8 T cell",
        "GZMK+ CD27+ EM CD8 T cell",
        "GZMK- CD27+ EM CD8 T cell",
        "Core naive CD8 T cell",
        "CM CD8 T cell",
    ],
    "CD4 T cells": [
        "KLRF1- GZMB+ CD27- memory CD4 T cell",
        "GZMB- CD27+ EM CD4 T cell",
        "GZMB- CD27- EM CD4 T cell",
        "Core naive CD4 T cell",
        "CM CD4 T cell",
    ],
    "B cells": [
        "Type 2 polarized memory B cell",
        "Early memory B cell",
        "Transitional B cell",
        "Core naive B cell",
        "Core memory B cell",
        "CD95 memory B cell",
        "CD27+ effector B cell",
        "CD27- effector B cell",
    ],
}
SHORT_STREAM_LABELS = {
    "KLRF1+ GZMB+ CD27- EM CD8 T cell": "KLRF1+ GZMB+ EM CD8 T",
    "KLRF1- GZMB+ CD27- EM CD8 T cell": "KLRF1− GZMB+ EM CD8 T",
    "GZMK+ CD27+ EM CD8 T cell": "GZMK+ CD27+ EM CD8 T",
    "GZMK- CD27+ EM CD8 T cell": "GZMK− CD27+ EM CD8 T",
    "Core naive CD8 T cell": "Core naive CD8 T",
    "CM CD8 T cell": "CM CD8 T",
    "KLRF1- GZMB+ CD27- memory CD4 T cell": "KLRF1− GZMB+ memory CD4 T",
    "GZMB- CD27+ EM CD4 T cell": "GZMB− CD27+ EM CD4 T",
    "GZMB- CD27- EM CD4 T cell": "GZMB− CD27− EM CD4 T",
    "Core naive CD4 T cell": "Core naive CD4 T",
    "CM CD4 T cell": "CM CD4 T",
    "Type 2 polarized memory B cell": "Type 2 polarized memory B",
    "Early memory B cell": "Early memory B",
    "Transitional B cell": "Transitional B",
    "Core naive B cell": "Core naive B",
    "Core memory B cell": "Core memory B",
    "CD95 memory B cell": "CD95 memory B",
    "CD27+ effector B cell": "CD27+ effector B",
    "CD27- effector B cell": "CD27− effector B",
}
LONGITUDINAL_ORDER = [
    "Adaptive NK cell",
    "KLRF1- GZMB+ CD27- EM CD8 T cell",
    "KLRF1- GZMB+ CD27- memory CD4 T cell",
    "KLRF1+ GZMB+ CD27- EM CD8 T cell",
    "KLRF1+ effector Vd1 gdT",
    "KLRF1- effector Vd1 gdT",
]
CURVE_CELL_ORDER = [
    "CM CD4 T",
    "CM CD8 T",
    "Core naive CD4 T",
    "Core naive CD8 T",
    "GZMB- CD27- EM CD4 T",
    "GZMB- CD27+ EM CD4 T",
    "GZMK+ CD27+ EM CD8 T",
    "Naive CD4 Treg",
]
CURVE_LABELS = {
    "CM CD4 T": "CM CD4 T",
    "CM CD8 T": "CM CD8 T",
    "Core naive CD4 T": "Core naive\nCD4 T",
    "Core naive CD8 T": "Core naive\nCD8 T",
    "GZMB- CD27- EM CD4 T": "GZMB− CD27−\nEM CD4 T",
    "GZMB- CD27+ EM CD4 T": "GZMB− CD27+\nEM CD4 T",
    "GZMK+ CD27+ EM CD8 T": "GZMK+ CD27+\nEM CD8 T",
    "Naive CD4 Treg": "Naive CD4\nTreg",
}
DATASET_ORDER = ["Follow up\n10x Flex", "Onek1k\n10x 3'", "Terekhova\n10x 5'"]
DATASET_LABELS = ["Follow-up · 10x Flex", "OneK1K · 10x 3′", "Terekhova · 10x 5′"]


matplotlib.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
    }
)


def load_colors():
    colors = {}
    with COLOR_DATA.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["xpos", "label", "color"]:
            raise ValueError("Unexpected cell-type color columns")
        for row in reader:
            colors[row["label"].strip()] = row["color"].strip()
    if len(colors) != 71:
        raise ValueError("Expected 71 cell-type colors")
    return colors


def color_for(label, colors):
    return colors.get(label, colors.get(label + " cell", "#6C7A89"))


def contrasting_text(color):
    red, green, blue = to_rgb(color)
    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    return "white" if luminance < 0.48 else "#172027"


def validate_columns(frame, columns, expected_rows):
    if list(frame.columns) != columns or len(frame) != expected_rows:
        raise ValueError("Unexpected data columns or row count")
    if frame.isna().any().any():
        raise ValueError("Required plotting data contain missing values")


def smooth_composition(frame, categories):
    ages = np.arange(40, 91, dtype=float)
    pivot = frame.pivot(index="Ages", columns="celltypist_l3", values="percentage")
    pivot = pivot.reindex(index=ages, columns=categories).interpolate(axis=0, limit_direction="both")
    values = pivot.to_numpy(dtype=float).T
    values = gaussian_filter1d(values, sigma=3.0, axis=1, mode="nearest")
    values = np.clip(values, 0, None)
    values = values / values.sum(axis=0, keepdims=True) * 100
    return ages, values


def add_stream_labels(axis, ages, values, categories, colors):
    cumulative = np.cumsum(values, axis=0)
    lower = np.vstack((np.zeros(values.shape[1]), cumulative[:-1]))
    for index, category in enumerate(categories):
        available = (ages >= 46) & (ages <= 85)
        thickness = values[index].copy()
        thickness[~available] = -1
        position = int(np.argmax(thickness))
        if thickness[position] < 7.2:
            continue
        x = ages[position]
        y = lower[index, position] + values[index, position] / 2
        axis.text(
            x,
            y,
            SHORT_STREAM_LABELS[category],
            fontsize=9.2,
            fontweight=500,
            color=contrasting_text(color_for(category, colors)),
            ha="center",
            va="center",
            clip_on=True,
        )


def draw_streamgraph(frame, group_name, categories, colors, output_path):
    ages, values = smooth_composition(frame, categories)
    palette = [color_for(category, colors) for category in categories]
    figure, axis = plt.subplots(figsize=(13.5, 8.2))
    figure.subplots_adjust(left=0.085, right=0.975, top=0.825, bottom=0.225)
    axis.stackplot(ages, values, colors=palette, edgecolor="#202A31", linewidth=0.75)
    add_stream_labels(axis, ages, values, categories, colors)
    axis.set_xlim(40, 90)
    axis.set_ylim(0, 100)
    axis.set_xticks(np.arange(40, 91, 10))
    axis.set_yticks(np.arange(0, 101, 20))
    axis.yaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    axis.set_xlabel("Age (years)", fontsize=12, labelpad=8)
    axis.set_ylabel("Share within " + group_name, fontsize=12, labelpad=10)
    axis.tick_params(axis="both", labelsize=10, colors="#34414A")
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.spines["left"].set_color("#56616A")
    axis.spines["bottom"].set_color("#56616A")
    axis.grid(axis="y", color="white", linewidth=0.8, alpha=0.48)
    axis.set_axisbelow(False)
    figure.text(0.085, 0.944, group_name + " composition across age", fontsize=21, fontweight="bold", color="#202A31", ha="left")
    figure.text(0.085, 0.902, "Smoothed proportional trajectories from ages 40 to 90", fontsize=10.5, color="#697680", ha="left")
    handles = [Patch(facecolor=color, edgecolor="none") for color in palette]
    labels = [SHORT_STREAM_LABELS[category] for category in categories]
    figure.legend(
        handles,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.53, 0.035),
        ncol=3 if len(categories) <= 6 else 4,
        frameon=False,
        fontsize=9.1,
        handlelength=1.15,
        columnspacing=1.6,
    )
    figure.savefig(output_path, dpi=300)
    plt.close(figure)


def linear_fit_with_ci(x, y, grid):
    coefficients = np.polyfit(x, y, 1)
    prediction = np.polyval(coefficients, grid)
    fitted = np.polyval(coefficients, x)
    degrees = max(len(x) - 2, 1)
    residual_scale = math.sqrt(float(np.sum((y - fitted) ** 2)) / degrees)
    centered = float(np.sum((x - np.mean(x)) ** 2))
    if centered <= 0:
        error = np.full_like(grid, residual_scale)
    else:
        error = residual_scale * np.sqrt(1 / len(x) + (grid - np.mean(x)) ** 2 / centered)
    critical = float(t.ppf(0.975, degrees)) if degrees > 1 else 1.96
    return prediction, prediction - critical * error, prediction + critical * error


def p_text(value):
    if value < 0.001:
        return f"{value:.1e}"
    return f"{value:.3f}".rstrip("0").rstrip(".")


def add_density(axis, values, color, y_grid):
    if len(values) < 3 or np.ptp(values) == 0:
        return
    density = gaussian_kde(values)(y_grid)
    if density.max() > 0:
        density = density / density.max()
    axis.fill_betweenx(y_grid, 0, density, color=color, alpha=0.34, linewidth=0)
    axis.plot(density, y_grid, color=color, linewidth=1.1)


def draw_longitudinal(frame, colors):
    figure = plt.figure(figsize=(14.5, 15.8))
    outer = figure.add_gridspec(3, 2, left=0.07, right=0.975, top=0.875, bottom=0.075, wspace=0.19, hspace=0.30)
    for index, cell_type in enumerate(LONGITUDINAL_ORDER):
        row = index // 2
        column = index % 2
        inner = outer[row, column].subgridspec(1, 2, width_ratios=[12, 1.3], wspace=0.04)
        axis = figure.add_subplot(inner[0, 0])
        density_axis = figure.add_subplot(inner[0, 1], sharey=axis)
        subset = frame[frame["AIFI_L3"].eq(cell_type)].copy()
        y_values = subset["AIFI_L3_clr"].to_numpy(dtype=float)
        y_padding = max(np.ptp(y_values) * 0.10, 0.35)
        y_limits = (float(y_values.min() - y_padding), float(y_values.max() + y_padding))
        y_grid = np.linspace(y_limits[0], y_limits[1], 180)
        for age_group in ("Young", "Older"):
            color = AGE_GROUP_COLORS[age_group]
            group_data = subset[subset["Age Group"].eq(age_group)]
            for _, subject_data in group_data.groupby("subject.subjectGuid"):
                ordered = subject_data.sort_values("sample.daysSinceFirstVisit")
                axis.plot(
                    ordered["sample.daysSinceFirstVisit"],
                    ordered["AIFI_L3_clr"],
                    color=color,
                    linewidth=0.45,
                    alpha=0.22,
                    zorder=1,
                )
            x = group_data["sample.daysSinceFirstVisit"].to_numpy(dtype=float)
            y = group_data["AIFI_L3_clr"].to_numpy(dtype=float)
            grid = np.linspace(x.min(), x.max(), 160)
            prediction, lower, upper = linear_fit_with_ci(x, y, grid)
            axis.fill_between(grid, lower, upper, color=color, alpha=0.13, linewidth=0, zorder=2)
            axis.plot(grid, prediction, color=color, linewidth=2.0, zorder=3)
            correlation, probability = spearmanr(x, y)
            line_index = 0 if age_group == "Young" else 1
            axis.text(
                0.035,
                0.92 - line_index * 0.075,
                f"{age_group}: ρ = {correlation:.2f}, p = {p_text(probability)}",
                transform=axis.transAxes,
                fontsize=9.2,
                color=color,
                ha="left",
                va="top",
                zorder=5,
            )
            add_density(density_axis, y, color, y_grid)
        axis.set_xlim(-20, 620)
        axis.set_ylim(*y_limits)
        axis.set_xticks([0, 200, 400, 600])
        axis.yaxis.set_major_locator(MaxNLocator(nbins=5))
        axis.tick_params(labelsize=9, colors="#3E4951")
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.grid(axis="y", color="#E4E8EB", linewidth=0.65)
        strip_color = color_for(cell_type, colors)
        axis.add_patch(Rectangle((0, 1.01), 1, 0.14, transform=axis.transAxes, facecolor=strip_color, edgecolor="none", clip_on=False))
        title = "\n".join(textwrap.wrap(cell_type, width=31))
        axis.text(
            0.5,
            1.08,
            title,
            transform=axis.transAxes,
            ha="center",
            va="center",
            fontsize=9.2,
            fontweight=500,
            color=contrasting_text(strip_color),
            linespacing=1.0,
            clip_on=False,
        )
        density_axis.set_xlim(0, 1.05)
        density_axis.axis("off")
    legend = [Line2D([0], [0], color=AGE_GROUP_COLORS[group], linewidth=2.6, label=group) for group in ("Young", "Older")]
    figure.legend(legend, [item.get_label() for item in legend], loc="upper right", bbox_to_anchor=(0.975, 0.925), frameon=False, ncol=2, fontsize=10)
    figure.text(0.07, 0.958, "Longitudinal immune-cell dynamics", fontsize=22, fontweight="bold", color="#202A31", ha="left")
    figure.text(0.07, 0.925, "Individual trajectories, age-group linear fits, 95% confidence intervals and marginal densities", fontsize=10.5, color="#697680", ha="left")
    figure.text(0.51, 0.026, "Time since first visit (days)", fontsize=12, color="#303A42", ha="center")
    figure.text(0.018, 0.48, "Centered log-ratio abundance", fontsize=12, color="#303A42", ha="center", va="center", rotation=90)
    figure.savefig(LONGITUDINAL_OUTPUT, dpi=300)
    plt.close(figure)


def loess_fit(x, y, grid, span=0.8):
    order = np.argsort(x)
    x = np.asarray(x, dtype=float)[order]
    y = np.asarray(y, dtype=float)[order]
    count = len(x)
    neighborhood = max(6, int(math.ceil(span * count)))
    prediction = np.empty_like(grid, dtype=float)
    standard_error = np.empty_like(grid, dtype=float)
    for index, target in enumerate(grid):
        distance = np.abs(x - target)
        bandwidth = float(np.partition(distance, min(neighborhood - 1, count - 1))[min(neighborhood - 1, count - 1)])
        if bandwidth <= 0:
            positive = distance[distance > 0]
            bandwidth = float(positive.min()) if positive.size else 1.0
        scaled = np.clip(distance / bandwidth, 0, 1)
        weights = (1 - scaled ** 3) ** 3
        centered = x - target
        design = np.column_stack((np.ones(count), centered, centered ** 2))
        root_weights = np.sqrt(weights)
        weighted_design = design * root_weights[:, None]
        weighted_y = y * root_weights
        coefficients = np.linalg.lstsq(weighted_design, weighted_y, rcond=None)[0]
        prediction[index] = coefficients[0]
        residuals = y - design @ coefficients
        effective = max(int(np.count_nonzero(weights > 0)) - 3, 1)
        variance = float(np.sum(weights * residuals ** 2) / effective)
        covariance = np.linalg.pinv(weighted_design.T @ weighted_design)
        standard_error[index] = math.sqrt(max(variance * covariance[0, 0], 0))
    critical = 1.96
    return prediction, prediction - critical * standard_error, prediction + critical * standard_error


def draw_curve_grid(frame, colors):
    figure, axes = plt.subplots(3, 8, figsize=(19.2, 8.8), squeeze=False)
    figure.subplots_adjust(left=0.075, right=0.965, top=0.81, bottom=0.13, wspace=0.39, hspace=0.42)
    for row_index, dataset in enumerate(DATASET_ORDER):
        for column_index, cell_type in enumerate(CURVE_CELL_ORDER):
            axis = axes[row_index, column_index]
            subset = frame[frame["Dataset"].eq(dataset) & frame["celltype"].eq(cell_type)]
            x = subset["Ages"].to_numpy(dtype=float)
            y = subset["RNA_Age_Metric_Up"].to_numpy(dtype=float)
            grid = np.linspace(float(x.min()), float(x.max()), 150)
            prediction, lower, upper = loess_fit(x, y, grid)
            color = color_for(cell_type, colors)
            axis.fill_between(grid, lower, upper, color="#AAB1B6", alpha=0.48, linewidth=0)
            axis.plot(grid, prediction, color=color, linewidth=2.3)
            correlation, probability = spearmanr(x, y)
            axis.text(
                0.96,
                0.06,
                f"ρ = {correlation:.2f}\np = {p_text(probability)}",
                transform=axis.transAxes,
                ha="right",
                va="bottom",
                fontsize=7.8,
                color=color,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.76, "pad": 1.2},
            )
            axis.set_xlim(39, 91)
            axis.set_xticks([40, 50, 60, 70, 80, 90])
            if row_index < 2:
                axis.set_xticklabels([])
            else:
                axis.tick_params(axis="x", labelsize=7.5)
            axis.yaxis.set_major_locator(MaxNLocator(nbins=4))
            axis.yaxis.tick_right()
            axis.tick_params(axis="y", labelsize=7.2, pad=2)
            axis.spines["top"].set_visible(False)
            axis.spines["left"].set_visible(False)
            axis.spines["right"].set_color("#3E474D")
            axis.spines["bottom"].set_color("#3E474D")
            axis.grid(axis="y", color="#EBEEF0", linewidth=0.55)
            if row_index == 0:
                axis.set_title(
                    CURVE_LABELS[cell_type],
                    fontsize=8.5,
                    fontweight=500,
                    color=contrasting_text(color),
                    pad=7,
                    linespacing=1.0,
                    bbox={"facecolor": color, "edgecolor": "none", "boxstyle": "square,pad=0.38"},
                )
    row_positions = [0.695, 0.465, 0.235]
    for label, position in zip(DATASET_LABELS, row_positions):
        figure.text(0.025, position, label, fontsize=9.8, fontweight=500, color="#303A42", ha="center", va="center", rotation=90)
    figure.text(0.075, 0.958, "RNA age metric trajectories", fontsize=22, fontweight="bold", color="#202A31", ha="left")
    figure.text(0.075, 0.918, "Local quadratic fits with 95% confidence intervals across three independent datasets", fontsize=10.5, color="#697680", ha="left")
    figure.text(0.52, 0.055, "Age (years)", fontsize=11.5, color="#303A42", ha="center")
    figure.text(0.992, 0.47, "RNA age metric (upregulated genes)", fontsize=11.5, color="#303A42", ha="center", va="center", rotation=270)
    figure.savefig(CURVE_OUTPUT, dpi=300)
    plt.close(figure)


def main():
    colors = load_colors()
    stream_data = pd.read_excel(PROFILE_DATA, sheet_name="Fig2c_d_e")
    validate_columns(stream_data, ["Ages", "celltypist_l3", "percentage"], 968)
    for group_name, categories in STREAM_GROUPS.items():
        selected = stream_data[stream_data["celltypist_l3"].isin(categories)]
        draw_streamgraph(selected, group_name, categories, colors, STREAM_OUTPUTS[group_name])
    longitudinal = pd.read_excel(LONGITUDINAL_DATA, sheet_name="Fig3b")
    validate_columns(
        longitudinal,
        ["AIFI_L3", "subject.subjectGuid", "Age Group", "sample.daysSinceFirstVisit", "AIFI_L3_clr"],
        1463,
    )
    draw_longitudinal(longitudinal, colors)
    curves = pd.read_excel(PROFILE_DATA, sheet_name="Fig2f_g")
    validate_columns(curves, ["pbmc_sample_id", "Ages", "RNA_Age_Metric_Up", "celltype", "Dataset"], 10248)
    draw_curve_grid(curves, colors)


if __name__ == "__main__":
    main()
