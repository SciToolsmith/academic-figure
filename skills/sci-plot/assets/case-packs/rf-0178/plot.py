from pathlib import Path
import csv
import numpy as np
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import LogLocator, FuncFormatter
from scipy import stats


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data.csv"
OUTPUT_PATH = BASE_DIR / "plot_python.png"
GROUPS = ("WGS", "MAG", "SAG")
COLORS = {"WGS": "#374955", "MAG": "#8C6BB1", "SAG": "#247BA0"}


def read_data(path):
    length = []
    cds = []
    completeness = []
    group = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        expected = {"completeness", "number_of_cds", "type", "length"}
        if reader.fieldnames is None or not expected.issubset(set(reader.fieldnames)):
            raise ValueError("data.csv does not contain the expected columns")
        for row in reader:
            length.append(float(row["length"]))
            cds.append(float(row["number_of_cds"]))
            completeness.append(float(row["completeness"]))
            group.append(row["type"].strip())
    length = np.asarray(length, dtype=float)
    cds = np.asarray(cds, dtype=float)
    completeness = np.asarray(completeness, dtype=float)
    group = np.asarray(group, dtype=str)
    if len(length) == 0:
        raise ValueError("data.csv contains no observations")
    if not np.all(np.isfinite(length)) or not np.all(np.isfinite(cds)) or not np.all(np.isfinite(completeness)):
        raise ValueError("data.csv contains non-finite numeric values")
    if np.any(length <= 0) or np.any(cds <= 0):
        raise ValueError("length and number_of_cds must be positive")
    unexpected = sorted(set(group) - set(GROUPS))
    if unexpected:
        raise ValueError(f"Unexpected genome types: {unexpected}")
    return length, cds, completeness, group


def holm_adjust(p_values):
    p_values = np.asarray(p_values, dtype=float)
    order = np.argsort(p_values)
    adjusted_sorted = np.maximum.accumulate((len(p_values) - np.arange(len(p_values))) * p_values[order])
    adjusted = np.empty_like(adjusted_sorted)
    adjusted[order] = np.minimum(adjusted_sorted, 1.0)
    return adjusted


def scientific(value):
    return f"{value:.2e}".replace("e-0", "e−").replace("e+0", "e+").replace("e-", "e−")


length, cds, completeness, group = read_data(DATA_PATH)
x = np.log10(length)
y = np.log10(cds)
fit = stats.linregress(x, y)
fitted = fit.intercept + fit.slope * x
residual = y - fitted
n = len(x)
x_grid = np.linspace(x.min(), x.max(), 500)
y_grid = fit.intercept + fit.slope * x_grid
sse = np.sum(residual ** 2)
sxx = np.sum((x - x.mean()) ** 2)
sigma2 = sse / (n - 2)
se_mean = np.sqrt(sigma2 * (1 / n + (x_grid - x.mean()) ** 2 / sxx))
t_critical = stats.t.ppf(0.975, n - 2)
lower = y_grid - t_critical * se_mean
upper = y_grid + t_critical * se_mean
pairs = (("WGS", "MAG"), ("WGS", "SAG"), ("MAG", "SAG"))
raw_p = []
effect_sizes = []
for first, second in pairs:
    first_values = residual[group == first]
    second_values = residual[group == second]
    result = stats.mannwhitneyu(first_values, second_values, alternative="two-sided")
    raw_p.append(result.pvalue)
    effect_sizes.append(2 * result.statistic / (len(first_values) * len(second_values)) - 1)
adjusted_p = holm_adjust(raw_p)
residual_span = residual.max() - residual.min()
residual_limits = (residual.min() - 0.035 * residual_span, residual.max() + 0.035 * residual_span)

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 11,
        "axes.labelsize": 12,
        "axes.titlesize": 13,
        "axes.linewidth": 0.8,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
        "figure.facecolor": "#F7F5F1",
        "axes.facecolor": "#FFFFFF",
        "savefig.facecolor": "#F7F5F1",
    }
)

fig = plt.figure(figsize=(16, 12.5), dpi=360)
grid = fig.add_gridspec(
    3,
    3,
    width_ratios=(5.5, 5.5, 2.25),
    height_ratios=(1.15, 5.4, 2.65),
    left=0.075,
    right=0.965,
    bottom=0.125,
    top=0.89,
    wspace=0.08,
    hspace=0.18,
)
ax_main = fig.add_subplot(grid[1, :2])
ax_top = fig.add_subplot(grid[0, :2])
ax_summary = fig.add_subplot(grid[0, 2])
ax_right = fig.add_subplot(grid[1, 2])
ax_residual = fig.add_subplot(grid[2, :2])
ax_stats = fig.add_subplot(grid[2, 2])

x_bins = np.linspace(x.min(), x.max(), 30)
y_bins = np.linspace(y.min(), y.max(), 30)
for name in GROUPS:
    selected = group == name
    ax_top.hist(
        x[selected],
        bins=x_bins,
        density=True,
        histtype="stepfilled",
        color=COLORS[name],
        alpha=0.10,
        linewidth=0,
    )
    ax_top.hist(
        x[selected],
        bins=x_bins,
        density=True,
        histtype="step",
        color=COLORS[name],
        alpha=0.95,
        linewidth=1.35,
    )
    ax_right.hist(
        y[selected],
        bins=y_bins,
        density=True,
        histtype="stepfilled",
        orientation="horizontal",
        color=COLORS[name],
        alpha=0.10,
        linewidth=0,
    )
    ax_right.hist(
        y[selected],
        bins=y_bins,
        density=True,
        histtype="step",
        orientation="horizontal",
        color=COLORS[name],
        alpha=0.95,
        linewidth=1.35,
    )
    ax_main.scatter(
        length[selected],
        cds[selected],
        s=12,
        color=COLORS[name],
        alpha=0.38,
        edgecolors="none",
        rasterized=True,
        zorder=2,
    )

ax_main.fill_between(10 ** x_grid, 10 ** lower, 10 ** upper, color="#B44E4A", alpha=0.14, linewidth=0, zorder=1)
ax_main.plot(10 ** x_grid, 10 ** y_grid, color="#9C3D3A", linewidth=2.2, zorder=4)
ax_main.set_xscale("log")
ax_main.set_yscale("log")
ax_main.set_xlabel("Genome length (bp)", labelpad=9)
ax_main.set_ylabel("Number of coding sequences (CDS)", labelpad=9)
ax_main.grid(which="major", color="#D7D5CF", linewidth=0.65, alpha=0.65)
ax_main.grid(which="minor", color="#EAE8E3", linewidth=0.4, alpha=0.45)
ax_main.set_axisbelow(True)
ax_main.xaxis.set_major_locator(LogLocator(base=10, numticks=7))
ax_main.yaxis.set_major_locator(LogLocator(base=10, numticks=7))
ax_main.text(
    0.025,
    0.965,
    f"Global descriptive OLS on log₁₀ scale\nslope = {fit.slope:.4f}   R² = {fit.rvalue ** 2:.4f}   n = {n:,}",
    transform=ax_main.transAxes,
    ha="left",
    va="top",
    fontsize=11,
    color="#25333B",
    bbox={"boxstyle": "round,pad=0.55", "facecolor": "#FFFFFF", "edgecolor": "#D8D5CE", "alpha": 0.94},
    zorder=6,
)
ax_main.text(
    0.975,
    0.035,
    "Shaded band: 95% confidence interval for the fitted mean on the log₁₀ scale",
    transform=ax_main.transAxes,
    ha="right",
    va="bottom",
    fontsize=9.5,
    color="#5A6469",
)

ax_top.set_ylabel("Density", fontsize=10)
ax_top.set_xlim(x.min(), x.max())
ax_top.tick_params(axis="x", which="both", bottom=False, labelbottom=False)
ax_top.tick_params(axis="y", labelsize=9)
ax_top.spines["top"].set_visible(False)
ax_top.spines["right"].set_visible(False)
ax_top.spines["bottom"].set_visible(False)
ax_top.grid(axis="y", color="#E3E0DA", linewidth=0.55)
ax_top.text(0.01, 0.88, "Marginal distributions", transform=ax_top.transAxes, fontsize=10.5, weight="bold", color="#34434B")

ax_right.set_xlabel("Density", fontsize=10)
ax_right.set_ylim(y.min(), y.max())
ax_right.tick_params(axis="y", which="both", left=False, labelleft=False)
ax_right.tick_params(axis="x", labelsize=9)
ax_right.spines["top"].set_visible(False)
ax_right.spines["right"].set_visible(False)
ax_right.spines["left"].set_visible(False)
ax_right.grid(axis="x", color="#E3E0DA", linewidth=0.55)

ax_summary.axis("off")
legend_handles = [
    Line2D([0], [0], marker="o", linestyle="", markerfacecolor=COLORS[name], markeredgecolor="none", markersize=7, label=f"{name}  n = {np.sum(group == name):,}")
    for name in GROUPS
]
legend_handles.append(Line2D([0], [0], color="#9C3D3A", linewidth=2.2, label="Global OLS fit"))
ax_summary.legend(handles=legend_handles, loc="center left", frameon=False, handlelength=2.1, borderaxespad=0)

box_data = [residual[group == name] for name in GROUPS]
box = ax_residual.boxplot(
    box_data,
    vert=False,
    positions=np.arange(1, len(GROUPS) + 1),
    widths=0.48,
    showfliers=False,
    patch_artist=True,
    medianprops={"color": "#17252C", "linewidth": 1.8},
    whiskerprops={"color": "#66747A", "linewidth": 1.1},
    capprops={"color": "#66747A", "linewidth": 1.1},
    boxprops={"edgecolor": "#66747A", "linewidth": 1.0},
)
for patch, name in zip(box["boxes"], GROUPS):
    patch.set_facecolor(COLORS[name])
    patch.set_alpha(0.30)
rng = np.random.default_rng(20260727)
for position, name in enumerate(GROUPS, start=1):
    values = residual[group == name]
    jitter = rng.uniform(-0.18, 0.18, size=len(values))
    ax_residual.scatter(values, position + jitter, s=7, color=COLORS[name], alpha=0.14, edgecolors="none", rasterized=True)
ax_residual.axvline(0, color="#9C3D3A", linewidth=1.4, linestyle=(0, (4, 3)))
ax_residual.set_xlim(residual_limits)
ax_residual.set_yticks(np.arange(1, len(GROUPS) + 1), GROUPS)
ax_residual.set_xlabel("Residual: observed − fitted log₁₀(CDS)", labelpad=8)
ax_residual.set_title("Residual distributions by genome type", loc="left", pad=10, weight="bold", color="#25333B")
ax_residual.grid(axis="x", color="#E1DED8", linewidth=0.6)
ax_residual.set_axisbelow(True)
ax_residual.spines["top"].set_visible(False)
ax_residual.spines["right"].set_visible(False)

ax_stats.axis("off")
median_lines = "\n".join(
    f"{name}   median {np.median(residual[group == name]):+.4f}" for name in GROUPS
)
comparison_lines = "\n".join(
    f"{first}–{second}   Holm p = {scientific(value)}   δ = {effect:+.3f}"
    for (first, second), value, effect in zip(pairs, adjusted_p, effect_sizes)
)
ax_stats.text(0.0, 0.97, "Residual summary", ha="left", va="top", fontsize=11.5, weight="bold", color="#25333B")
ax_stats.text(0.0, 0.79, median_lines, ha="left", va="top", fontsize=10, color="#3E4A50", linespacing=1.65)
ax_stats.text(0.0, 0.47, "Exploratory pairwise tests", ha="left", va="top", fontsize=10.5, weight="bold", color="#25333B")
ax_stats.text(0.0, 0.34, comparison_lines, ha="left", va="top", fontsize=9.8, color="#3E4A50", linespacing=1.65)
ax_stats.text(
    0.0,
    0.01,
    "Two-sided Mann–Whitney U tests; Holm adjustment.\nδ: rank-biserial effect, first group minus second.",
    ha="left",
    va="bottom",
    fontsize=8.9,
    color="#687277",
    linespacing=1.45,
)

fig.suptitle(
    "Genome length and coding-sequence abundance",
    x=0.075,
    y=0.955,
    ha="left",
    fontsize=23,
    weight="bold",
    color="#1F2D34",
)
fig.text(
    0.075,
    0.918,
    "A global log–log relationship with group-resolved marginal and residual distributions",
    ha="left",
    va="center",
    fontsize=12.5,
    color="#59666C",
)
fig.text(
    0.075,
    0.055,
    "Analysis note. Each row is treated as one independent observation. The global OLS model uses genome length as the sole predictor; "
    "the completeness column is retained in the source data but is not included in this model. The classical OLS confidence interval assumes "
    "homoscedastic residuals. Pairwise residual tests are exploratory and do not establish causality.",
    ha="left",
    va="bottom",
    fontsize=9.5,
    color="#5D676C",
    wrap=True,
)
fig.savefig(OUTPUT_PATH, dpi=360, bbox_inches="tight", pad_inches=0.18)
plt.close(fig)
