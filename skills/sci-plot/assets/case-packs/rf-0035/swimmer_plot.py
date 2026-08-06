from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "swimmer_data.xlsx"
OUTPUT_PATH = BASE_DIR / "swimmer_plot.png"


def load_data():
    data = pd.read_excel(DATA_PATH, sheet_name="Sheet2")
    response_column = "Comfirmed best overall response"
    data = data.loc[data[response_column].notna()].copy()
    data = data.loc[data[response_column].astype(str).str.upper().ne("NA")].copy()
    time_columns = [
        "first_partial_response",
        "first_stable_disease",
        "first_progressive_disease",
        "last_follow_up",
    ]
    for column in time_columns:
        data[column] = pd.to_numeric(data[column], errors="coerce")
        data.loc[data[column] < 0, column] = np.nan
        data[column] = data[column] / 30.0
    data["death_event"] = data["death"].notna()
    data["follow_up_event"] = data["follow up"].notna()
    response_names = {
        "PR": "Partial response",
        "SD": "Stable disease",
        "PD": "Progressive disease",
    }
    data["response"] = data[response_column].astype(str).str.upper().map(response_names)
    return data.sort_values("last_follow_up", ascending=True, kind="stable").reset_index(drop=True)


def main():
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 11.5,
            "axes.labelcolor": "#27323A",
            "axes.edgecolor": "#27323A",
            "text.color": "#27323A",
            "xtick.color": "#53616A",
            "ytick.color": "#53616A",
        }
    )
    data = load_data()
    response_colors = {
        "Partial response": "#E4A19C",
        "Stable disease": "#9FAFD3",
        "Progressive disease": "#8FBEA6",
    }
    y = np.arange(len(data))
    fig, ax = plt.subplots(figsize=(13.2, 10.2), dpi=300)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    for index, row in data.iterrows():
        ax.barh(
            index,
            row["last_follow_up"],
            height=0.58,
            color=response_colors[row["response"]],
            edgecolor="white",
            linewidth=0.7,
            zorder=2,
        )
    event_styles = [
        ("first_partial_response", "^", "#B80C46", "#B80C46", "First partial response", 46),
        ("first_stable_disease", "D", "white", "#E6373E", "First stable disease", 36),
        ("first_progressive_disease", "v", "#148554", "#148554", "First progressive disease", 46),
    ]
    for column, marker, face, edge, label, size in event_styles:
        subset = data[column].notna()
        ax.scatter(
            data.loc[subset, column],
            y[subset],
            marker=marker,
            s=size,
            facecolor=face,
            edgecolor=edge,
            linewidth=1.25,
            zorder=4,
            label=label,
        )
    death = data["death_event"]
    follow_up = data["follow_up_event"]
    ax.scatter(
        data.loc[death, "last_follow_up"] + 0.18,
        y[death],
        marker="s",
        s=38,
        facecolor="#04A2C4",
        edgecolor="white",
        linewidth=0.7,
        zorder=5,
    )
    ax.scatter(
        data.loc[follow_up, "last_follow_up"] + 0.18,
        y[follow_up],
        marker="D",
        s=39,
        facecolor="#70B83F",
        edgecolor="white",
        linewidth=0.7,
        zorder=5,
    )
    ax.set_xlim(0, 46)
    ax.set_ylim(-0.8, len(data) - 0.2)
    ax.set_xticks(np.arange(0, 47, 5))
    ax.set_yticks(y)
    ax.set_yticklabels([f"P{int(value):02d}" for value in data["id"]], fontsize=9.5)
    ax.set_xlabel("Time since treatment initiation (months)", fontsize=13.5, fontweight="bold", labelpad=12)
    ax.set_ylabel("Patient", fontsize=13.5, fontweight="bold", labelpad=11)
    ax.tick_params(axis="x", labelsize=10.5, length=5, width=0.9)
    ax.tick_params(axis="y", length=0, pad=7)
    ax.xaxis.grid(True, color="#DEE3E6", linewidth=0.7, zorder=0)
    ax.yaxis.grid(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(1.0)
    ax.spines["bottom"].set_linewidth(1.0)
    fig.suptitle(
        "Treatment response over time",
        x=0.09,
        y=0.97,
        ha="left",
        fontsize=22,
        fontweight="bold",
    )
    fig.text(
        0.09,
        0.925,
        f"Duration and first documented response events for {len(data)} patients",
        ha="left",
        fontsize=12.5,
        color="#64737B",
    )
    event_handles = [
        Line2D([0], [0], marker="^", linestyle="None", markerfacecolor="#B80C46", markeredgecolor="#B80C46", markersize=7, label="First partial response"),
        Line2D([0], [0], marker="D", linestyle="None", markerfacecolor="white", markeredgecolor="#E6373E", markeredgewidth=1.3, markersize=6.5, label="First stable disease"),
        Line2D([0], [0], marker="v", linestyle="None", markerfacecolor="#148554", markeredgecolor="#148554", markersize=7, label="First progressive disease"),
        Line2D([0], [0], marker="s", linestyle="None", markerfacecolor="#04A2C4", markeredgecolor="white", markersize=7, label="Death"),
        Line2D([0], [0], marker="D", linestyle="None", markerfacecolor="#70B83F", markeredgecolor="white", markersize=7, label="Follow-up"),
    ]
    response_handles = [
        Patch(facecolor=response_colors[name], edgecolor="none", label=name)
        for name in ("Partial response", "Stable disease", "Progressive disease")
    ]
    first_legend = ax.legend(
        handles=event_handles,
        title="Clinical events",
        loc="upper left",
        bbox_to_anchor=(1.015, 0.98),
        frameon=False,
        fontsize=10.5,
        title_fontsize=11.5,
        borderaxespad=0,
        handletextpad=0.7,
        labelspacing=0.9,
    )
    first_legend.get_title().set_fontweight("bold")
    ax.add_artist(first_legend)
    second_legend = ax.legend(
        handles=response_handles,
        title="Confirmed best\noverall response",
        loc="upper left",
        bbox_to_anchor=(1.015, 0.63),
        frameon=False,
        fontsize=10.5,
        title_fontsize=11.5,
        borderaxespad=0,
        handlelength=1.4,
        handletextpad=0.7,
        labelspacing=0.9,
    )
    second_legend.get_title().set_fontweight("bold")
    fig.subplots_adjust(left=0.09, right=0.75, top=0.88, bottom=0.105)
    fig.savefig(OUTPUT_PATH, dpi=300, facecolor="white", metadata={"Software": "Matplotlib"})
    plt.close(fig)


if __name__ == "__main__":
    main()
