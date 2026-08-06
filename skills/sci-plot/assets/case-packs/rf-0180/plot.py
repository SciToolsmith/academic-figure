from pathlib import Path
import csv
import numpy as np
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

root = Path(__file__).resolve().parent
expected_columns = [
    "runaway_id",
    "spectral_type",
    "spt_short",
    "phot_g_mean_mag",
    "v_t",
    "v_t_error",
    "v_t_error_plus",
    "v_t_error_min",
    "t_kin",
    "t_kin_error_plus",
    "t_kin_error_min",
]
with (root / "data.csv").open(newline="", encoding="utf-8-sig") as handle:
    reader = csv.DictReader(handle)
    rows = list(reader)
    columns = reader.fieldnames
if columns != expected_columns or len(rows) != 55:
    raise ValueError("Unexpected data.csv schema or row count")
if len({row["runaway_id"] for row in rows}) != len(rows):
    raise ValueError("runaway_id must be unique")
numeric_columns = [name for name in expected_columns if name not in {"spectral_type", "spt_short"}]
for row in rows:
    for name in numeric_columns:
        row[name] = float(row[name])
values = np.asarray([[row[name] for name in numeric_columns] for row in rows], dtype=float)
if not np.isfinite(values).all():
    raise ValueError("Numeric fields must be finite")
error_columns = ["v_t_error", "v_t_error_plus", "v_t_error_min", "t_kin_error_plus", "t_kin_error_min"]
if any(row[name] <= 0 for row in rows for name in error_columns):
    raise ValueError("Uncertainty fields must be positive")
if any(row["v_t"] - row["v_t_error_min"] <= 0 for row in rows):
    raise ValueError("Log-scale velocity intervals must remain positive")

category_order = ["wnh", "o2", "o3", "o4", "o5", "o6", "o7", "o8", "o9", "borlater", "unk"]
category_labels = {
    "wnh": "WN(h)",
    "o2": "O2",
    "o3": "O3",
    "o4": "O4",
    "o5": "O5",
    "o6": "O6",
    "o7": "O7",
    "o8": "O8",
    "o9": "O9",
    "borlater": "B or later",
    "unk": "Unknown",
}
category_colors = dict(
    zip(
        category_order,
        ["#6C5B7B", "#0072B2", "#56B4E9", "#009E73", "#7A9E3A", "#E3A11A", "#E07A2D", "#D95F45", "#A33A3A", "#8A5A44", "#8A9094"],
    )
)
if {row["spt_short"] for row in rows} != set(category_order):
    raise ValueError("Unexpected spectral class")

def magnitude_group(value):
    if value > 15:
        return "> 15", "o"
    if value < 13:
        return "< 13", "D"
    return "13 to 15", "s"

t_kin = np.asarray([row["t_kin"] for row in rows])
bin_width = 0.15
bandwidth = 0.20
bin_edges = np.arange(0, 3.0 + bin_width / 2, bin_width)
histogram, _ = np.histogram(t_kin, bins=bin_edges)
kde_grid = np.linspace(0, 3.0, 600)
z = (kde_grid[:, None] - t_kin[None, :]) / bandwidth
kde_density = np.exp(-0.5 * z**2).mean(axis=1) / (bandwidth * np.sqrt(2 * np.pi))
kde_scaled = kde_density * len(rows) * bin_width
mag_counts = {
    "> 15": sum(row["phot_g_mean_mag"] > 15 for row in rows),
    "13 to 15": sum(13 <= row["phot_g_mean_mag"] <= 15 for row in rows),
    "< 13": sum(row["phot_g_mean_mag"] < 13 for row in rows),
}

bg = "#F7F6F2"
ink = "#17242C"
muted = "#58676D"
grid_color = "#D8DAD6"
mpl.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.edgecolor": "#69767B",
        "axes.linewidth": 0.8,
        "text.color": ink,
        "axes.labelcolor": ink,
        "xtick.color": "#354248",
        "ytick.color": "#354248",
        "figure.facecolor": bg,
        "axes.facecolor": bg,
        "savefig.facecolor": bg,
    }
)
figure = plt.figure(figsize=(13.4, 9.6))
grid = figure.add_gridspec(
    2,
    2,
    height_ratios=[1.25, 4.35],
    width_ratios=[4.5, 1.35],
    left=0.085,
    right=0.965,
    bottom=0.14,
    top=0.84,
    hspace=0.22,
    wspace=0.22,
)
distribution = figure.add_subplot(grid[0, 0])
summary = figure.add_subplot(grid[0, 1])
scatter = figure.add_subplot(grid[1, 0])
key = figure.add_subplot(grid[1, 1])

distribution.bar(
    bin_edges[:-1],
    histogram,
    width=bin_width,
    align="edge",
    color="#D98067",
    edgecolor=bg,
    linewidth=1.0,
    alpha=0.88,
)
distribution.plot(kde_grid, kde_scaled, color=ink, linewidth=2.0)
distribution.set_xlim(0, 3.0)
distribution.set_ylim(0, max(float(histogram.max()), float(kde_scaled.max())) * 1.18)
distribution.set_ylabel("Objects per 0.15 Myr")
distribution.set_xticks(np.arange(0, 3.01, 0.5))
distribution.grid(axis="y", color=grid_color, linewidth=0.55)
distribution.spines[["top", "right"]].set_visible(False)
distribution.set_title("a   Kinematic-age distribution", loc="left", fontsize=12.5, fontweight="bold", pad=10)
distribution.legend(
    handles=[
        Line2D([0], [0], color="#D98067", linewidth=7, label="Histogram"),
        Line2D([0], [0], color=ink, linewidth=2, label="Gaussian KDE, bw = 0.20 Myr"),
    ],
    loc="upper right",
    frameon=False,
    fontsize=8,
)

summary.axis("off")
summary.text(0.02, 0.96, "Dataset overview", ha="left", va="top", fontsize=11.5, fontweight="bold")
summary.text(
    0.02,
    0.76,
    f"{len(rows)} objects\n{len(category_order)} supplied spectral classes",
    ha="left",
    va="top",
    fontsize=9,
    color=muted,
    linespacing=1.5,
)
summary.text(0.02, 0.39, "Photometric G strata", ha="left", va="top", fontsize=8.4, fontweight="bold")
summary.text(
    0.02,
    0.25,
    f"> 15: {mag_counts['> 15']}    13 to 15: {mag_counts['13 to 15']}    < 13: {mag_counts['< 13']}",
    ha="left",
    va="top",
    fontsize=7.8,
    color=muted,
)

scatter.set_yscale("log")
scatter.set_xlim(0, 4.0)
scatter.set_ylim(18, 220)
scatter.set_xticks(np.arange(0, 4.01, 0.5))
scatter.set_yticks([20, 30, 50, 100, 200])
scatter.get_yaxis().set_major_formatter(mpl.ticker.ScalarFormatter())
scatter.get_yaxis().set_minor_formatter(mpl.ticker.NullFormatter())
scatter.grid(color=grid_color, linewidth=0.55)
scatter.spines[["top", "right"]].set_visible(False)
scatter.axhline(27.6, color="#37474D", linestyle=(0, (5, 3)), linewidth=1.0, zorder=0)
scatter.text(
    3.96,
    27.6 * 1.035,
    "27.6 km s$^{-1}$ reference threshold",
    ha="right",
    va="bottom",
    fontsize=7.4,
    color="#37474D",
)
for row in rows:
    _, marker = magnitude_group(row["phot_g_mean_mag"])
    scatter.errorbar(
        row["t_kin"],
        row["v_t"],
        xerr=np.asarray([[row["t_kin_error_min"]], [row["t_kin_error_plus"]]]),
        yerr=np.asarray([[row["v_t_error_min"]], [row["v_t_error_plus"]]]),
        fmt="none",
        ecolor="#6E777B",
        elinewidth=0.85,
        alpha=0.62,
        capsize=1.8,
        capthick=0.75,
        zorder=1,
    )
    scatter.scatter(
        row["t_kin"],
        row["v_t"],
        s=52,
        marker=marker,
        facecolor=category_colors[row["spt_short"]],
        edgecolor=ink,
        linewidth=0.55,
        zorder=2,
    )
scatter.set_xlabel("Kinematic age (Myr)")
scatter.set_ylabel("Transverse velocity (km s$^{-1}$)")
scatter.set_title("b   Velocity with asymmetric uncertainty in both axes", loc="left", fontsize=12.5, fontweight="bold", pad=10)

key.axis("off")
spectral_handles = [
    Line2D(
        [0],
        [0],
        marker="o",
        linestyle="",
        markersize=6,
        markerfacecolor=category_colors[category],
        markeredgecolor=ink,
        markeredgewidth=0.5,
        label=category_labels[category],
    )
    for category in category_order
]
spectral_legend = key.legend(
    handles=spectral_handles,
    title="Discrete spectral class",
    loc="upper left",
    bbox_to_anchor=(0, 1.0),
    frameon=False,
    fontsize=7.8,
    title_fontsize=9,
    borderaxespad=0,
    handletextpad=0.7,
    labelspacing=0.55,
)
key.add_artist(spectral_legend)
magnitude_handles = [
    Line2D([0], [0], marker="o", linestyle="", markersize=6, markerfacecolor="#FFFFFF", markeredgecolor=ink, label="G > 15"),
    Line2D([0], [0], marker="s", linestyle="", markersize=6, markerfacecolor="#FFFFFF", markeredgecolor=ink, label="13 <= G <= 15"),
    Line2D([0], [0], marker="D", linestyle="", markersize=6, markerfacecolor="#FFFFFF", markeredgecolor=ink, label="G < 13"),
]
key.legend(
    handles=magnitude_handles,
    title="Photometric G stratum",
    loc="lower left",
    bbox_to_anchor=(0, 0.01),
    frameon=False,
    fontsize=7.8,
    title_fontsize=9,
    borderaxespad=0,
    handletextpad=0.7,
    labelspacing=0.65,
)

figure.text(
    0.055,
    0.965,
    "Kinematic age and transverse velocity in the supplied runaway-star sample",
    ha="left",
    va="top",
    fontsize=18,
    fontweight="bold",
)
figure.text(
    0.055,
    0.925,
    "All 55 objects are shown; colours are categorical, while marker shape records the supplied photometric-magnitude stratum.",
    ha="left",
    va="top",
    fontsize=9.3,
    color=muted,
)
figure.text(
    0.055,
    0.048,
    "Asymmetric lower/upper uncertainties come directly from t_kin_error_min/plus and v_t_error_min/plus. The 27.6 km s^-1 line is a reference threshold from the original workflow, not an estimate from these data.",
    ha="left",
    va="bottom",
    fontsize=8.0,
    color=muted,
)
figure.text(
    0.055,
    0.025,
    "The density curve is descriptive only and uses a fixed 0.20-Myr Gaussian bandwidth, scaled to the 0.15-Myr histogram-bin count.",
    ha="left",
    va="bottom",
    fontsize=8.0,
    color=muted,
)
figure.savefig(root / "plot_python.png", dpi=360)
plt.close(figure)
