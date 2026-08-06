from pathlib import Path
import csv

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "faceted_stacked_bar_data.csv"
OUTPUT_PATH = BASE_DIR / "faceted_stacked_bar.png"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "savefig.facecolor": "white",
    "figure.facecolor": "white",
})

days = ["Day 0", "Day 7", "Day 10", "Day 31"]
legend_order = [
    "Microbe_7", "Microbe_4", "Microbe_2", "Microbe_9", "Microbe_5",
    "Microbe_8", "Microbe_1", "Microbe_3", "Microbe_6", "Microbe_10",
]
stack_order = list(reversed(legend_order))
colors = {
    "Microbe_1": "#D3D1D2",
    "Microbe_2": "#CC79A8",
    "Microbe_3": "#7AC0EA",
    "Microbe_4": "#0EA079",
    "Microbe_5": "#68C49D",
    "Microbe_6": "#EACEDF",
    "Microbe_7": "#5AB4E5",
    "Microbe_8": "#D99BBB",
    "Microbe_9": "#98D1F0",
    "Microbe_10": "#7F7F7F",
}

records = []
with DATA_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
    for row in csv.DictReader(handle):
        records.append({
            "source_type": row["source_type"],
            "source_seed": int(row["source_seed"]),
            "sample_id": int(row["sample_id"]),
            "day": row["day"],
            "microbe": row["microbe"],
            "relative_abundance": float(row["relative_abundance"]),
        })

if len(records) != 240 or {row["source_type"] for row in records} != {"simulated"}:
    raise ValueError("Expected 240 simulated composition records")
if {row["source_seed"] for row in records} != {123}:
    raise ValueError("Expected R simulation seed 123")

composition = {}
for row in records:
    key = (row["day"], row["sample_id"])
    composition.setdefault(key, {})[row["microbe"]] = row["relative_abundance"]

for values in composition.values():
    if set(values) != set(legend_order) or abs(sum(values.values()) - 1.0) > 1e-10:
        raise ValueError("Each sample must contain ten microbes summing to one")

fig, axes = plt.subplots(
    1,
    4,
    figsize=(12, 6.8),
    dpi=200,
    sharey=True,
    gridspec_kw={"wspace": 0.045},
)
fig.subplots_adjust(left=0.09, right=0.78, bottom=0.18, top=0.79)
fig.text(0.09, 0.945, "Microbial community composition", fontsize=20, fontweight="bold", color="#20262E")
fig.text(0.09, 0.902, "Vehicle cohort · simulated composition generated with R seed 123", fontsize=11.5, color="#63707C")

for panel_index, (axis, day) in enumerate(zip(axes, days)):
    samples = sorted(sample for current_day, sample in composition if current_day == day)
    bottom = [0.0] * len(samples)
    for microbe in stack_order:
        heights = [composition[(day, sample)][microbe] for sample in samples]
        axis.bar(
            range(len(samples)),
            heights,
            width=0.92,
            bottom=bottom,
            color=colors[microbe],
            edgecolor="white",
            linewidth=0.45,
        )
        bottom = [base + height for base, height in zip(bottom, heights)]
    axis.set_xlim(-0.55, len(samples) - 0.45)
    axis.set_ylim(0, 1)
    axis.set_xticks([])
    axis.set_xlabel(day, fontsize=12, fontweight="bold", labelpad=13, color="#2F3740")
    axis.set_axisbelow(True)
    axis.grid(axis="y", color="#E5E8EB", linewidth=0.65)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.spines["bottom"].set_color("#2F3740")
    axis.spines["bottom"].set_linewidth(1.05)
    if panel_index == 0:
        axis.spines["left"].set_color("#2F3740")
        axis.spines["left"].set_linewidth(1.05)
        axis.set_ylabel("Relative abundance", fontsize=12.5, fontweight="bold", labelpad=10, color="#2F3740")
        axis.set_yticks([0, 0.25, 0.5, 0.75, 1])
        axis.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        axis.tick_params(axis="y", labelsize=10.5, colors="#4E5965", length=4, width=0.9)
    else:
        axis.spines["left"].set_visible(False)
        axis.tick_params(axis="y", left=False, labelleft=False)

handles = [Patch(facecolor=colors[name], edgecolor="none", label=name) for name in legend_order]
legend = fig.legend(
    handles=handles,
    title="Family",
    loc="upper left",
    bbox_to_anchor=(0.805, 0.79),
    frameon=False,
    fontsize=10.5,
    title_fontsize=12,
    handlelength=1.05,
    handleheight=1.05,
    labelspacing=0.58,
    borderaxespad=0,
)
legend._legend_box.align = "left"

fig.savefig(OUTPUT_PATH, dpi=200, bbox_inches="tight", pad_inches=0.18, metadata={"Software": "Matplotlib"})
plt.close(fig)
