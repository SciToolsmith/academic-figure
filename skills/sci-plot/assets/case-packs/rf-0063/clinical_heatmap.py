from collections import Counter
from pathlib import Path
import csv
import math

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import LinearSegmentedColormap, Normalize, to_rgba
from matplotlib.patches import Patch
import numpy as np


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "clinical_heatmap_data.tsv"
OUTPUT_PATH = BASE_DIR / "clinical_heatmap.png"


matplotlib.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
    }
)


def number(value):
    if value is None or str(value).strip() in {"", "NA", "NaN"}:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def load_rows():
    with DATA_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = list(reader)
    required = {
        "patient_id",
        "mrd_status",
        "mrd_ctDNA_ppm_log",
        "mol_ml_peudolog",
        "cfdna_input_ng",
        "main_histology",
        "Stage",
        "lesion1_size_pathology",
        "pack_years_truncated",
        "luad_subtype",
        "oncogenic_event",
    }
    missing = required.difference(reader.fieldnames or [])
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    if len(rows) != 171 or len({row["patient_id"] for row in rows}) != 171:
        raise ValueError("Expected 171 unique patients")
    for row in rows:
        row["oncogenic_event"] = "None" if row["oncogenic_event"] in {"", "NA"} else row["oncogenic_event"]
        row["luad_subtype"] = "NA" if row["luad_subtype"] in {"", "NA"} else row["luad_subtype"].title()
    rows.sort(key=lambda row: (0 if row["main_histology"] == "LUAD" else 1, number(row["mrd_ctDNA_ppm_log"]) or 0.0))
    return rows


def numeric_array(rows, key):
    return np.asarray([np.nan if number(row[key]) is None else number(row[key]) for row in rows], dtype=float)


def colors_for_categories(rows, key, palette, fallback="#D9D9D9"):
    return np.asarray([to_rgba(palette.get(row[key], fallback)) for row in rows], dtype=float)


def colors_for_values(values, cmap, minimum, maximum, missing="#D9D9D9"):
    norm = Normalize(minimum, maximum, clip=True)
    result = []
    for value in values:
        result.append(to_rgba(missing) if not np.isfinite(value) else cmap(norm(value)))
    return np.asarray(result, dtype=float)


def style_bar_axis(axis, ticks, labels):
    axis.set_yticks(ticks)
    axis.set_yticklabels(labels, fontsize=7.5, color="#38434C")
    axis.tick_params(axis="y", width=0.7, length=3, pad=2)
    axis.tick_params(axis="x", bottom=False, labelbottom=False)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.spines["left"].set_color("#7E878E")
    axis.spines["bottom"].set_color("#7E878E")
    axis.grid(axis="y", color="#E8EBED", linewidth=0.65, zorder=0)
    axis.set_axisbelow(True)


def draw_track(figure, bounds, colors):
    axis = figure.add_axes(bounds)
    axis.imshow(colors[np.newaxis, :, :], aspect="auto", interpolation="nearest")
    axis.set_xticks([])
    axis.set_yticks([])
    for spine in axis.spines.values():
        spine.set_visible(False)
    return axis


def add_legend(figure, handles, title, anchor, columns=1):
    legend = figure.legend(
        handles=handles,
        loc="lower left",
        bbox_to_anchor=anchor,
        ncol=columns,
        frameon=False,
        fontsize=8.5,
        title=title,
        title_fontsize=9.5,
        handlelength=1.0,
        handleheight=0.9,
        handletextpad=0.45,
        columnspacing=0.9,
        borderaxespad=0,
        labelspacing=0.35,
    )
    legend._legend_box.align = "left"


def add_colorbar(figure, cmap, limits, ticks, label, bounds):
    axis = figure.add_axes(bounds)
    colorbar = figure.colorbar(ScalarMappable(norm=Normalize(*limits), cmap=cmap), cax=axis, orientation="horizontal")
    colorbar.set_ticks(ticks)
    colorbar.ax.tick_params(labelsize=8.0, length=2.0, pad=1.5, colors="#38434C")
    colorbar.outline.set_visible(False)
    figure.text(bounds[0], bounds[1] + bounds[3] + 0.008, label, fontsize=9.3, fontweight="bold", color="#28323A", ha="left")


def draw_heatmap(rows):
    count = len(rows)
    x = np.arange(count)
    left = 0.058
    width = 0.738
    right_label = left + width + 0.010
    histology_palette = {"LUAD": "#D0BB7E", "Non-LUAD": "#91C7BA"}
    stage_palette = {"I": "#E8EAF5", "II": "#7AA8CE", "III": "#345C9F"}
    subtype_palette = {
        "Invasive Mucinous": "#EAB874",
        "Lepidic": "#A6C7DB",
        "Papillary": "#4B7BB1",
        "Acinar": "#B3D291",
        "Cribriform": "#6CA956",
        "Micropapillary": "#DE9493",
        "Solid": "#CA2E2E",
    }
    event_palette = {"None": "#E5E5E5", "EGFR mutated": "#602A84", "MET exon 14 skipped": "#CCAC68"}
    ctdna_palette = {"Detected": "#8FD0F3", "Not Detected": "#BFC2C5"}
    size_cmap = LinearSegmentedColormap.from_list("tumor_size", ["#F7F8FC", "#A5A9C8", "#2F386E"])
    smoking_cmap = LinearSegmentedColormap.from_list("smoking", ["#F7F7F7", "#A7A7A7", "#171717"])
    figure = plt.figure(figsize=(20, 11.5))
    figure.text(left, 0.958, "Clinicopathological landscape of early-stage lung cancer", fontsize=22, fontweight="bold", color="#20272D", ha="left")
    figure.text(left, 0.925, "171 patients ordered by histology and preoperative ctDNA abundance", fontsize=10.8, color="#64717B", ha="left")

    ctdna_values = numeric_array(rows, "mrd_ctDNA_ppm_log")
    molecule_values = numeric_array(rows, "mol_ml_peudolog")
    input_values = numeric_array(rows, "cfdna_input_ng")
    axis_ctdna = figure.add_axes([left, 0.735, width, 0.145])
    axis_ctdna.bar(x, ctdna_values, width=0.82, color=[ctdna_palette[row["mrd_status"]] for row in rows], edgecolor="none", zorder=2)
    axis_ctdna.set_xlim(-0.6, count - 0.4)
    axis_ctdna.set_ylim(0, 5.65)
    style_bar_axis(axis_ctdna, [0, 1, 2, 3, 4, 5], ["0", "10", "100", "1,000", "10,000", "100,000"])

    axis_molecule = figure.add_axes([left, 0.655, width, 0.072], sharex=axis_ctdna)
    axis_molecule.bar(x, molecule_values, width=0.82, color="#3C5488", edgecolor="none", zorder=2)
    axis_molecule.set_ylim(0, 5.9)
    style_bar_axis(axis_molecule, [0, 1, 3, 5], ["0", "10", "1,000", "100,000"])

    histology_colors = colors_for_categories(rows, "main_histology", histology_palette)
    stage_colors = colors_for_categories(rows, "Stage", stage_palette)
    size_values = numeric_array(rows, "lesion1_size_pathology")
    smoking_values = numeric_array(rows, "pack_years_truncated")
    subtype_colors = colors_for_categories(rows, "luad_subtype", subtype_palette)
    event_colors = colors_for_categories(rows, "oncogenic_event", event_palette)
    tracks = [
        (0.616, histology_colors, "Histology"),
        (0.577, stage_colors, "pTNM stage"),
        (0.538, colors_for_values(size_values, size_cmap, 5, 120), "Tumor size (mm)"),
        (0.499, colors_for_values(smoking_values, smoking_cmap, 0, 136), "Smoking (pack years)"),
        (0.460, subtype_colors, "LUAD subtype"),
        (0.421, event_colors, "Oncogenic event"),
    ]
    for bottom, colors, label in tracks:
        draw_track(figure, [left, bottom, width, 0.032], colors)
        figure.text(right_label, bottom + 0.016, label, fontsize=9.7, color="#2A333A", va="center", ha="left")

    axis_input = figure.add_axes([left, 0.337, width, 0.076], sharex=axis_ctdna)
    axis_input.bar(x, input_values, width=0.78, color="#B09C85", edgecolor="none", zorder=2)
    axis_input.set_ylim(0, 52)
    style_bar_axis(axis_input, [0, 20, 40], ["0", "20", "40"])
    figure.text(right_label, 0.375, "Input cfDNA (ng)", fontsize=9.7, color="#2A333A", va="center", ha="left")

    axis_ids = figure.add_axes([left, 0.292, width, 0.038], sharex=axis_ctdna)
    axis_ids.set_xlim(-0.6, count - 0.4)
    axis_ids.set_ylim(0, 1)
    axis_ids.set_xticks(x)
    axis_ids.set_xticklabels([row["patient_id"].replace("CRUK", "") for row in rows], rotation=90, fontsize=5.0, color="#364047")
    axis_ids.tick_params(axis="x", length=0, pad=1)
    axis_ids.set_yticks([])
    for spine in axis_ids.spines.values():
        spine.set_visible(False)
    figure.text(right_label, 0.311, "CRUK ID", fontsize=9.7, color="#2A333A", va="center", ha="left")

    split = sum(row["main_histology"] == "LUAD" for row in rows) - 0.5
    for axis in [axis_ctdna, axis_molecule, axis_input]:
        axis.axvline(split, color="white", linewidth=2.2, zorder=5)
    for bottom, _, _ in tracks:
        separator = figure.add_axes([left + width * (split + 0.5) / count - 0.0006, bottom, 0.0012, 0.032])
        separator.set_facecolor("white")
        separator.set_xticks([])
        separator.set_yticks([])
        for spine in separator.spines.values():
            spine.set_visible(False)

    figure.text(right_label, 0.807, "ctDNA (PPM)", fontsize=10.0, fontweight="bold", color="#2A333A", va="center", ha="left")
    figure.text(right_label, 0.691, "Tumor molecules/mL", fontsize=10.0, fontweight="bold", color="#2A333A", va="center", ha="left")

    add_legend(figure, [Patch(color=color, label=label) for label, color in histology_palette.items()], "Histology", (0.058, 0.155))
    add_legend(figure, [Patch(color=color, label=label) for label, color in ctdna_palette.items()], "ctDNA", (0.150, 0.155))
    add_legend(figure, [Patch(color=color, label=label) for label, color in stage_palette.items()], "pTNM stage", (0.260, 0.155))
    add_legend(figure, [Patch(color=color, label=label) for label, color in subtype_palette.items()], "LUAD subtype", (0.365, 0.125), columns=2)
    add_legend(figure, [Patch(color=color, label=label) for label, color in event_palette.items()], "Oncogenic event", (0.615, 0.145))
    add_colorbar(figure, size_cmap, (5, 120), [5, 50, 100, 120], "Tumor size (mm)", [0.058, 0.055, 0.145, 0.018])
    add_colorbar(figure, smoking_cmap, (0, 136), [0, 50, 100, 136], "Smoking (pack years)", [0.245, 0.055, 0.145, 0.018])
    figure.text(0.955, 0.055, "Bars and tracks share patient order", fontsize=7.6, color="#7A848C", ha="right")
    figure.savefig(OUTPUT_PATH, dpi=240)
    plt.close(figure)


def main():
    rows = load_rows()
    if Counter(row["main_histology"] for row in rows) != Counter({"LUAD": 94, "Non-LUAD": 77}):
        raise ValueError("Unexpected histology counts")
    draw_heatmap(rows)


if __name__ == "__main__":
    main()
