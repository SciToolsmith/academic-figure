from math import erfc, exp, sqrt
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "kaplan_meier_data.csv"
OUTPUT_PATH = BASE_DIR / "kaplan_meier.png"

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 10.5,
        "axes.labelcolor": "#27313A",
        "axes.titlecolor": "#17212B",
        "xtick.color": "#46515C",
        "ytick.color": "#46515C",
        "axes.linewidth": 0.9,
        "savefig.facecolor": "white",
    }
)

COLORS = {"Male": "#E35D42", "Female": "#3E7DBB"}
GROUPS = ["Male", "Female"]


def kaplan_meier(times, events):
    times = np.asarray(times, dtype=float)
    events = np.asarray(events, dtype=int)
    unique_times = np.unique(times)
    survival = 1.0
    curve = []
    for time in unique_times:
        at_risk = np.sum(times >= time)
        deaths = np.sum((times == time) & (events == 1))
        if deaths:
            survival *= 1.0 - deaths / at_risk
        curve.append((time, survival))
    return np.asarray(curve, dtype=float)


def survival_at(curve, query):
    index = np.searchsorted(curve[:, 0], query, side="right") - 1
    if index < 0:
        return 1.0
    return float(curve[index, 1])


def median_survival(curve):
    reached = curve[curve[:, 1] <= 0.5]
    return float(reached[0, 0]) if len(reached) else float("nan")


def logrank_p(time_a, event_a, time_b, event_b):
    event_times = np.unique(
        np.concatenate(
            [
                np.asarray(time_a)[np.asarray(event_a) == 1],
                np.asarray(time_b)[np.asarray(event_b) == 1],
            ]
        )
    )
    observed = 0.0
    expected = 0.0
    variance = 0.0
    for time in event_times:
        risk_a = np.sum(np.asarray(time_a) >= time)
        risk_b = np.sum(np.asarray(time_b) >= time)
        death_a = np.sum((np.asarray(time_a) == time) & (np.asarray(event_a) == 1))
        death_b = np.sum((np.asarray(time_b) == time) & (np.asarray(event_b) == 1))
        total_risk = risk_a + risk_b
        total_death = death_a + death_b
        observed += death_b
        expected += total_death * risk_b / total_risk
        if total_risk > 1:
            variance += (
                risk_a
                * risk_b
                * total_death
                * (total_risk - total_death)
                / (total_risk**2 * (total_risk - 1))
            )
    z_value = (observed - expected) / sqrt(variance)
    return erfc(abs(z_value) / sqrt(2))


def cox_binary(times, events, group):
    times = np.asarray(times, dtype=float)
    events = np.asarray(events, dtype=int)
    group = np.asarray(group, dtype=float)
    beta = 0.0
    information = 0.0
    for _ in range(80):
        score = 0.0
        information = 0.0
        for time in np.unique(times[events == 1]):
            risk = times >= time
            deaths = (times == time) & (events == 1)
            death_count = np.sum(deaths)
            weights = np.exp(beta * group[risk])
            denominator = np.sum(weights)
            probability = np.sum(weights * group[risk]) / denominator
            score += np.sum(group[deaths]) - death_count * probability
            information += death_count * probability * (1 - probability)
        change = score / information
        beta += change
        if abs(change) < 1e-11:
            break
    standard_error = sqrt(1 / information)
    return exp(beta), exp(beta - 1.96 * standard_error), exp(beta + 1.96 * standard_error)


data = pd.read_csv(DATA_PATH)
data["event_observed"] = data["event_observed"].astype(int)
curves = {}
medians = {}
for group in GROUPS:
    subset = data.loc[data["sex"] == group]
    curve = kaplan_meier(subset["time_months"], subset["event_observed"])
    curves[group] = curve
    medians[group] = median_survival(curve)

male = data.loc[data["sex"] == "Male"]
female = data.loc[data["sex"] == "Female"]
p_value = logrank_p(
    male["time_months"],
    male["event_observed"],
    female["time_months"],
    female["event_observed"],
)
hazard_ratio, hr_low, hr_high = cox_binary(
    data["time_months"],
    data["event_observed"],
    (data["sex"] == "Female").astype(int),
)

fig = plt.figure(figsize=(8.3, 6.9), dpi=240, facecolor="white")
grid = fig.add_gridspec(
    2,
    1,
    height_ratios=[4.6, 1.25],
    left=0.12,
    right=0.97,
    top=0.83,
    bottom=0.105,
    hspace=0.26,
)

fig.text(
    0.12,
    0.945,
    "Kaplan–Meier survival analysis",
    ha="left",
    va="top",
    fontsize=20,
    fontweight="bold",
    color="#17212B",
)
fig.text(
    0.12,
    0.897,
    f"Lung cancer example dataset  •  n = {len(data)}  •  {int(data['event_observed'].sum())} events",
    ha="left",
    va="top",
    fontsize=10.5,
    color="#697580",
)

ax = fig.add_subplot(grid[0])
for group in GROUPS:
    subset = data.loc[data["sex"] == group]
    curve = curves[group]
    x_values = np.concatenate([[0], curve[:, 0], [36]])
    y_values = np.concatenate([[1], curve[:, 1], [curve[-1, 1]]])
    ax.step(
        x_values,
        y_values,
        where="post",
        color=COLORS[group],
        lw=2.1,
        label=f"{group}  (n = {len(subset)})",
    )
    censored = subset.loc[subset["event_observed"] == 0, "time_months"].to_numpy()
    censor_survival = [survival_at(curve, time) for time in censored]
    ax.scatter(
        censored,
        censor_survival,
        marker="|",
        s=44,
        linewidths=1.1,
        color=COLORS[group],
        zorder=4,
    )

ax.axhline(0.5, color="#A8B0B7", lw=0.9, ls=(0, (4, 4)), zorder=0)
for group in GROUPS:
    median = medians[group]
    ax.vlines(median, 0, 0.5, color=COLORS[group], lw=1.0, linestyles=(0, (3, 3)), alpha=0.8)
    ax.text(
        median,
        0.535 if group == "Female" else 0.465,
        f"{median:.1f} mo",
        ha="center",
        va="bottom" if group == "Female" else "top",
        fontsize=9,
        color=COLORS[group],
        fontweight="bold",
    )

annotation = (
    f"Female vs Male\n"
    f"HR {hazard_ratio:.2f}  (95% CI {hr_low:.2f}–{hr_high:.2f})\n"
    f"Log-rank P = {p_value:.4f}"
)
ax.text(
    0.975,
    0.96,
    annotation,
    transform=ax.transAxes,
    ha="right",
    va="top",
    fontsize=9.4,
    linespacing=1.45,
    color="#27313A",
    bbox={"boxstyle": "round,pad=0.45", "facecolor": "white", "edgecolor": "#D4D9DE", "linewidth": 0.9},
)

ax.set_xlim(0, 36)
ax.set_ylim(0, 1.02)
ax.set_xticks(np.arange(0, 37, 6))
ax.set_yticks(np.arange(0, 1.01, 0.25))
ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
ax.set_xlabel("Time (months)", fontweight="bold", labelpad=8)
ax.set_ylabel("Survival probability", fontweight="bold", labelpad=8)
ax.grid(axis="y", color="#E5E8EB", linewidth=0.8)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.spines["left"].set_color("#27313A")
ax.spines["bottom"].set_color("#27313A")
ax.tick_params(length=4, width=0.85)
ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0.0, 0.03), handlelength=2.2)

table_ax = fig.add_subplot(grid[1])
table_ax.set_xlim(0, 36)
table_ax.set_ylim(-0.2, 2.35)
table_ax.axis("off")
risk_times = np.arange(0, 37, 6)
table_ax.text(
    -2.0,
    2.12,
    "Number at risk",
    ha="right",
    va="center",
    fontsize=9.6,
    fontweight="bold",
    color="#27313A",
    clip_on=False,
)
for row, group in zip([1.35, 0.38], GROUPS):
    subset = data.loc[data["sex"] == group]
    table_ax.scatter(
        [-1.35],
        [row],
        s=38,
        color=COLORS[group],
        clip_on=False,
    )
    table_ax.text(
        -1.85,
        row,
        group,
        ha="right",
        va="center",
        fontsize=9.4,
        color="#27313A",
        clip_on=False,
    )
    for time in risk_times:
        count = int(np.sum(subset["time_months"] >= time))
        table_ax.text(time, row, str(count), ha="center", va="center", fontsize=9.3, color="#27313A")

fig.text(
    0.12,
    0.035,
    "Data: ggsurvfit::df_lung, a formatted copy of the survival::lung example dataset",
    ha="left",
    va="bottom",
    fontsize=8.5,
    color="#7A858F",
)

fig.savefig(OUTPUT_PATH, dpi=240, bbox_inches="tight", pad_inches=0.08)
plt.close(fig)
