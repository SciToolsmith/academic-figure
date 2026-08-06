from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from scipy.stats import gaussian_kde

BASE_DIR = Path(__file__).resolve().parent
INPUT_PATH = BASE_DIR / "data.xlsx"
OUTPUT_PATH = BASE_DIR / "regional_age_raincloud.png"
REGION_ORDER = [
    "WesternEurope",
    "CentralEasternEurope",
    "SouthernEurope",
    "NorthernEurope",
    "CentralWesternAsia",
]
REGION_LABELS = {
    "WesternEurope": "Western Europe",
    "CentralEasternEurope": "Central/Eastern Europe",
    "SouthernEurope": "Southern Europe",
    "NorthernEurope": "Northern Europe",
    "CentralWesternAsia": "Central/Western Asia",
}
COLORS = {
    "WesternEurope": "#8FC4DD",
    "CentralEasternEurope": "#C5B783",
    "SouthernEurope": "#18A98B",
    "NorthernEurope": "#E44D55",
    "CentralWesternAsia": "#36413E",
}

data = pd.read_excel(INPUT_PATH, sheet_name="Sheet1")
required = ["Individual ID", "Region", "Age average"]
if list(data.columns) != required:
    raise ValueError("Workbook columns do not match the expected schema")
if data[required].isna().any().any():
    raise ValueError("Required fields contain missing values")
if data["Individual ID"].duplicated().any():
    raise ValueError("Individual identifiers must be unique")
if set(data["Region"]) != set(REGION_ORDER):
    raise ValueError("Workbook regions do not match the expected categories")
data["Age average"] = pd.to_numeric(data["Age average"], errors="raise")
if not np.isfinite(data["Age average"]).all() or (data["Age average"] <= 0).any():
    raise ValueError("Age values must be finite and positive")
data["age_kyr"] = data["Age average"] / 1000.0
axis_max = float(np.ceil(data["age_kyr"].max() / 5.0) * 5.0)

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.linewidth": 0.9,
        "axes.labelcolor": "#1D2723",
        "xtick.color": "#41504A",
        "ytick.color": "#1D2723",
        "figure.facecolor": "#FCFCFA",
        "axes.facecolor": "#FCFCFA",
        "savefig.facecolor": "#FCFCFA",
    }
)

fig, ax = plt.subplots(figsize=(10, 7.6))
row_gap = 1.30
y_positions = np.arange(len(REGION_ORDER))[::-1] * row_gap
grid = np.linspace(0, axis_max, 900)

for row_index, (region, base_y) in enumerate(zip(REGION_ORDER, y_positions)):
    subset = data.loc[data["Region"] == region].copy()
    values = subset["age_kyr"].to_numpy(dtype=float)
    bandwidth = values.std(ddof=1) * len(values) ** (-1.0 / 5.0)
    density = gaussian_kde(values, bw_method=bandwidth / values.std(ddof=1))(grid)
    density = density / density.max() * 0.42
    ax.fill_between(grid, base_y, base_y + density, color=COLORS[region], alpha=0.92, linewidth=0)
    ax.plot(grid, base_y + density, color=COLORS[region], linewidth=1.15)
    ax.hlines(base_y, 0, axis_max, color=COLORS[region], linewidth=0.75, alpha=0.75)

    q1, median, q3 = np.quantile(values, [0.25, 0.5, 0.75])
    iqr = q3 - q1
    lower = values[values >= q1 - 1.5 * iqr].min()
    upper = values[values <= q3 + 1.5 * iqr].max()
    box_center = base_y - 0.17
    box_height = 0.15
    ax.hlines(box_center, lower, upper, color="#3F4845", linewidth=1.05, zorder=4)
    ax.vlines([lower, upper], box_center - 0.055, box_center + 0.055, color="#3F4845", linewidth=1.0, zorder=4)
    ax.add_patch(
        Rectangle(
            (q1, box_center - box_height / 2),
            q3 - q1,
            box_height,
            facecolor=COLORS[region],
            edgecolor="#3F4845",
            linewidth=1.0,
            alpha=0.55,
            zorder=4,
        )
    )
    ax.vlines(median, box_center - box_height / 2, box_center + box_height / 2, color="#FCFCFA", linewidth=2.0, zorder=5)

    order = np.argsort(values, kind="stable")
    ranked_values = values[order]
    sequence = np.arange(len(ranked_values), dtype=float)
    point_x = ranked_values + 0.055 * np.sin(sequence * 2.399963)
    point_y = base_y - 0.39 - 0.22 * ((sequence * 0.61803398875) % 1.0)
    ax.scatter(
        point_x,
        point_y,
        s=7.5,
        facecolor="#6A716E",
        edgecolor="none",
        alpha=0.46,
        rasterized=True,
        zorder=3,
    )
    print(
        f"{region} | n={len(values)} | min={values.min():.4g} | "
        f"median={median:.4g} | max={values.max():.4g} kyr BP | Scott bandwidth={bandwidth:.4g} kyr"
    )

ax.set_yticks(
    y_positions,
    [f"{REGION_LABELS[region]}\n$n$={int((data['Region'] == region).sum()):,}" for region in REGION_ORDER],
)
ax.set_xlim(axis_max, 0)
ax.set_xticks(np.arange(axis_max, -0.1, -5))
ax.set_ylim(y_positions[-1] - 0.78, y_positions[0] + 0.72)
ax.set_xlabel("Age (kyr BP)")
ax.tick_params(axis="y", length=0, pad=12)
ax.tick_params(axis="x", length=4, width=0.8)
ax.spines[["top", "right", "left"]].set_visible(False)
ax.grid(axis="x", color="#DDE2DF", linewidth=0.65, alpha=0.75)
ax.set_axisbelow(True)
fig.suptitle(
    "Regional age distributions",
    x=0.22,
    y=0.965,
    ha="left",
    va="top",
    fontsize=18,
    fontweight="semibold",
    color="#17231F",
)
fig.text(
    0.22,
    0.915,
    f"{len(data):,} individuals · source ages converted from years to kyr BP · full {data['age_kyr'].min():.2f}–{data['age_kyr'].max():.2f} kyr range shown",
    ha="left",
    va="top",
    fontsize=9.3,
    color="#52605A",
)
fig.text(
    0.22,
    0.035,
    "Half-violin: Gaussian KDE (Scott bandwidth; each region normalized) · box: median, IQR and 1.5×IQR whiskers · dots: individuals",
    ha="left",
    va="bottom",
    fontsize=8.7,
    color="#52605A",
)
fig.subplots_adjust(left=0.22, right=0.975, top=0.86, bottom=0.12)
fig.savefig(OUTPUT_PATH, dpi=400, metadata={"Software": "Matplotlib"})
plt.close(fig)
if not OUTPUT_PATH.is_file() or OUTPUT_PATH.stat().st_size <= 0:
    raise OSError(f"Failed to create output: {OUTPUT_PATH}")
print(f"Saved: {OUTPUT_PATH}")
