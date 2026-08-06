from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import to_rgb
from matplotlib.patches import Circle, Rectangle


BASE_DIR = Path(__file__).resolve().parent


def locate_input(name):
    candidates = (BASE_DIR / name, BASE_DIR / "data" / name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Required input not found: {name}")


def blend(color_start, color_end, value):
    value = min(max(float(value), 0.0), 1.0)
    start = np.array(to_rgb(color_start))
    end = np.array(to_rgb(color_end))
    return tuple(start + (end - start) * value)


def contrast_text(color):
    red, green, blue = to_rgb(color)
    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    return "#FFFFFF" if luminance < 0.48 else "#1C1F21"


def draw_output_icon(axis, x, y, width, height, kind, color="#1F2528", linewidth=0.75):
    size = min(width, height) * 0.64
    left = x + (width - size) / 2
    bottom = y + (height - size) / 2
    if kind == "Features":
        gap = size * 0.08
        cell = (size - 2 * gap) / 3
        for row in range(3):
            for col in range(3):
                axis.add_patch(
                    Rectangle(
                        (left + col * (cell + gap), bottom + row * (cell + gap)),
                        cell,
                        cell,
                        facecolor="none",
                        edgecolor=color,
                        linewidth=linewidth,
                    )
                )
    elif kind == "Embedding":
        points = np.array(
            [
                [0.19, 0.20],
                [0.30, 0.38],
                [0.22, 0.59],
                [0.45, 0.25],
                [0.51, 0.49],
                [0.43, 0.72],
                [0.67, 0.34],
                [0.73, 0.61],
                [0.82, 0.77],
            ]
        )
        for px, py in points:
            axis.add_patch(
                Circle(
                    (left + px * size, bottom + py * size),
                    size * 0.047,
                    facecolor=color,
                    edgecolor="none",
                )
            )
        axis.plot(
            [left + 0.08 * size, left + 0.08 * size, left + 0.92 * size],
            [bottom + 0.92 * size, bottom + 0.08 * size, bottom + 0.08 * size],
            color=color,
            linewidth=linewidth,
            solid_capstyle="round",
        )
    elif kind == "Graph":
        points = np.array(
            [[0.18, 0.20], [0.17, 0.77], [0.51, 0.48], [0.82, 0.22], [0.83, 0.78]]
        )
        edges = ((0, 1), (0, 2), (1, 2), (2, 3), (2, 4), (3, 4))
        for source, target in edges:
            axis.plot(
                [left + points[source, 0] * size, left + points[target, 0] * size],
                [bottom + points[source, 1] * size, bottom + points[target, 1] * size],
                color=color,
                linewidth=linewidth,
            )
        for px, py in points:
            axis.add_patch(
                Circle(
                    (left + px * size, bottom + py * size),
                    size * 0.068,
                    facecolor=color,
                    edgecolor="none",
                )
            )


def main():
    summary = pd.read_csv(locate_input("scib_summary.csv"))
    column_info = pd.read_csv(locate_input("column_info.csv"), keep_default_na=False)
    column_groups = pd.read_csv(locate_input("column_group.csv"), keep_default_na=False)
    required_summary = {
        "method",
        "output",
        "features",
        "scaling",
        "avg_rank",
    }
    missing_summary = sorted(required_summary - set(summary.columns))
    if missing_summary:
        raise ValueError(f"Missing summary columns: {missing_summary}")
    metric_info = column_info.loc[
        column_info["geom"].eq("bar"), ["id", "id_color", "name", "group"]
    ].reset_index(drop=True)
    if metric_info.empty or metric_info[["id", "id_color", "group"]].eq("").any().any():
        raise ValueError("column_info.csv contains an incomplete metric definition")
    metric_columns = set(metric_info["id"]).union(metric_info["id_color"])
    missing_metrics = sorted(metric_columns - set(summary.columns))
    if missing_metrics:
        raise ValueError(f"Missing metric columns: {missing_metrics}")
    score_values = summary[metric_info["id"].tolist()]
    invalid_scores = ((score_values < 0) | (score_values > 1)) & score_values.notna()
    if invalid_scores.any().any():
        raise ValueError("Score values must lie within 0 and 1")
    group_order = [
        group
        for group in column_groups["group"].tolist()
        if group != "Method" and group in set(metric_info["group"])
    ]
    if set(group_order) != set(metric_info["group"]):
        raise ValueError("Metric groups do not match column_group.csv")
    summary = summary.assign(_source_order=np.arange(len(summary))).sort_values(
        ["avg_rank", "_source_order"], kind="stable", ignore_index=True
    )
    summary["display_rank"] = np.arange(1, len(summary) + 1)
    summary["feature_label"] = summary["features"].map({"HVG": "HVG", "Full": "FULL"})
    summary["scaling_label"] = summary["scaling"].map({"Scaled": "+", "Unscaled": "-"})
    if summary[["feature_label", "scaling_label"]].isna().any().any():
        raise ValueError("Unexpected features or scaling value")
    if not summary["output"].isin(["Features", "Embedding", "Graph"]).all():
        raise ValueError("Unexpected output value")
    for rank_column in metric_info["id_color"]:
        summary[f"_top_{rank_column}"] = summary[rank_column].rank(
            method="min", ascending=True, na_option="keep"
        )
    group_colors = {
        "RNA": ("#1D4E89", "#E8F0F6", "#DCE9F2"),
        "Simulations": ("#176B3A", "#E7F3E9", "#DDEEE2"),
        "Usability": ("#B45309", "#FCECD3", "#F7E4C7"),
        "Scalability": ("#3F454B", "#ECEDEF", "#E2E4E6"),
    }
    fallback_colors = ("#365F74", "#E8EFF2", "#E2EAED")
    rank_bounds = {}
    for group in group_order:
        rank_values = pd.concat(
            [
                summary[row["id_color"]]
                for _, row in metric_info.loc[metric_info["group"].eq(group)].iterrows()
            ],
            ignore_index=True,
        )
        rank_bounds[group] = (1.0, float(np.nanmax(rank_values.to_numpy(dtype=float))))
    left_columns = [
        ("Rank", 0.58),
        ("Method", 2.18),
        ("Output", 0.72),
        ("Features", 0.86),
        ("Scaling", 0.72),
    ]
    metric_widths = []
    for name in metric_info["name"]:
        metric_widths.append(1.22 if "human/mouse" in name.lower() else 0.96)
    widths = [width for _, width in left_columns] + metric_widths
    x_edges = np.concatenate(([0.0], np.cumsum(widths)))
    total_width = float(x_edges[-1])
    row_height = 0.49
    legend_height = 1.95
    label_height = 0.78
    group_height = 0.40
    title_height = 0.88
    data_height = len(summary) * row_height
    table_bottom = legend_height
    header_bottom = table_bottom + data_height
    group_bottom = header_bottom + label_height
    title_bottom = group_bottom + group_height
    total_height = title_bottom + title_height
    mpl.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8,
            "axes.linewidth": 0,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    figure, axis = plt.subplots(
        figsize=(total_width * 0.92, total_height * 0.92), facecolor="#FCFCFA"
    )
    axis.set_xlim(0, total_width)
    axis.set_ylim(0, total_height)
    axis.axis("off")
    axis.text(
        0,
        title_bottom + 0.62,
        "Benchmark summary of single-cell data integration methods",
        ha="left",
        va="center",
        fontsize=15.5,
        fontweight="bold",
        color="#1C2224",
    )
    axis.text(
        0,
        title_bottom + 0.25,
        "Twenty configurations ordered by average rank; visual encodings retain the source scores, ranks and missing values.",
        ha="left",
        va="center",
        fontsize=8.2,
        color="#596166",
    )
    method_span_end = x_edges[len(left_columns)]
    group_spans = {"Method": (0.0, method_span_end)}
    metric_start = len(left_columns)
    for group in group_order:
        indices = metric_info.index[metric_info["group"].eq(group)].tolist()
        first = metric_start + indices[0]
        last = metric_start + indices[-1] + 1
        group_spans[group] = (x_edges[first], x_edges[last])
    group_header_colors = {"Method": "#D9DAD7"}
    for group in group_order:
        group_header_colors[group] = group_colors.get(group, fallback_colors)[2]
    for group, (x_start, x_end) in group_spans.items():
        axis.add_patch(
            Rectangle(
                (x_start, group_bottom),
                x_end - x_start,
                group_height,
                facecolor=group_header_colors[group],
                edgecolor="#FFFFFF",
                linewidth=1.0,
            )
        )
        axis.text(
            (x_start + x_end) / 2,
            group_bottom + group_height / 2,
            group,
            ha="center",
            va="center",
            fontsize=8.8,
            fontweight="bold",
            color="#24292B",
        )
    header_labels = [name for name, _ in left_columns] + [
        str(name).replace("Immune (human/mouse)", "Immune\n(human /\nmouse)")
        .replace("Immune (human)", "Immune\n(human)")
        .replace("Mouse brain", "Mouse\nbrain")
        for name in metric_info["name"]
    ]
    for column_index, label in enumerate(header_labels):
        x_start = x_edges[column_index]
        width = widths[column_index]
        axis.add_patch(
            Rectangle(
                (x_start, header_bottom),
                width,
                label_height,
                facecolor="#F6F6F3",
                edgecolor="#FFFFFF",
                linewidth=0.8,
            )
        )
        axis.text(
            x_start + width / 2,
            header_bottom + label_height / 2,
            label,
            ha="center",
            va="center",
            fontsize=7.2,
            fontweight="semibold",
            linespacing=1.05,
            color="#343A3D",
        )
    for row_index, row in summary.iterrows():
        y_start = table_bottom + (len(summary) - 1 - row_index) * row_height
        row_color = "#F1F2F0" if row_index % 2 == 0 else "#FCFCFA"
        axis.add_patch(
            Rectangle(
                (0, y_start),
                total_width,
                row_height,
                facecolor=row_color,
                edgecolor="none",
            )
        )
        axis.text(
            x_edges[0] + widths[0] / 2,
            y_start + row_height / 2,
            str(int(row["display_rank"])),
            ha="center",
            va="center",
            fontsize=7.7,
            color="#202527",
        )
        axis.text(
            x_edges[1] + 0.10,
            y_start + row_height / 2,
            str(row["method"]),
            ha="left",
            va="center",
            fontsize=7.8,
            fontweight="semibold" if row_index < 3 else "normal",
            color="#1B2022",
        )
        draw_output_icon(
            axis,
            x_edges[2],
            y_start,
            widths[2],
            row_height,
            str(row["output"]),
        )
        feature_color = "#176B3A" if row["feature_label"] == "HVG" else "#63686B"
        axis.text(
            x_edges[3] + widths[3] / 2,
            y_start + row_height / 2,
            row["feature_label"],
            ha="center",
            va="center",
            fontsize=7.4,
            fontweight="semibold",
            color=feature_color,
        )
        axis.text(
            x_edges[4] + widths[4] / 2,
            y_start + row_height / 2,
            row["scaling_label"],
            ha="center",
            va="center",
            fontsize=9.3,
            fontweight="bold",
            color="#202527",
        )
        for metric_offset, (_, metric) in enumerate(metric_info.iterrows()):
            column_index = metric_start + metric_offset
            x_start = x_edges[column_index]
            width = widths[column_index]
            score = row[metric["id"]]
            rank_value = row[metric["id_color"]]
            inset_x = 0.07
            inset_y = 0.075
            cell_width = width - 2 * inset_x
            cell_height = row_height - 2 * inset_y
            axis.add_patch(
                Rectangle(
                    (x_start + inset_x, y_start + inset_y),
                    cell_width,
                    cell_height,
                    facecolor="#F5F5F2",
                    edgecolor="#B8BCBC",
                    linewidth=0.38,
                )
            )
            if pd.isna(score) or pd.isna(rank_value):
                axis.plot(
                    [
                        x_start + inset_x + 0.05,
                        x_start + inset_x + cell_width - 0.05,
                    ],
                    [
                        y_start + inset_y + 0.05,
                        y_start + inset_y + cell_height - 0.05,
                    ],
                    color="#A9ADAD",
                    linewidth=0.55,
                )
                axis.text(
                    x_start + width / 2,
                    y_start + row_height / 2,
                    "NA",
                    ha="center",
                    va="center",
                    fontsize=5.8,
                    color="#777D7F",
                )
                continue
            rank_minimum, rank_maximum = rank_bounds[metric["group"]]
            normalized_rank = (
                (float(rank_value) - rank_minimum) / (rank_maximum - rank_minimum)
                if rank_maximum > rank_minimum
                else 0.0
            )
            strong, pale, _ = group_colors.get(metric["group"], fallback_colors)
            fill = blend(strong, pale, normalized_rank)
            bar_width = cell_width * float(score)
            axis.add_patch(
                Rectangle(
                    (x_start + inset_x, y_start + inset_y),
                    bar_width,
                    cell_height,
                    facecolor=fill,
                    edgecolor="none",
                )
            )
            display_position = row[f"_top_{metric['id_color']}"]
            if pd.notna(display_position) and display_position <= 3:
                label = str(int(display_position))
                label_x = x_start + inset_x + max(
                    min(bar_width / 2, cell_width - 0.10), 0.10
                )
                axis.text(
                    label_x,
                    y_start + row_height / 2,
                    label,
                    ha="center",
                    va="center",
                    fontsize=7.1,
                    fontweight="bold",
                    color=contrast_text(fill),
                )
    for x_position in x_edges:
        axis.plot(
            [x_position, x_position],
            [table_bottom, group_bottom + group_height],
            color="#FFFFFF",
            linewidth=0.42,
            zorder=10,
        )
    for group, (x_start, x_end) in group_spans.items():
        axis.plot(
            [x_start, x_start],
            [table_bottom, group_bottom + group_height],
            color="#B8BCBC",
            linewidth=0.65,
            zorder=11,
        )
        if group == list(group_spans)[-1]:
            axis.plot(
                [x_end, x_end],
                [table_bottom, group_bottom + group_height],
                color="#B8BCBC",
                linewidth=0.65,
                zorder=11,
            )
    axis.plot(
        [0, total_width],
        [table_bottom, table_bottom],
        color="#9EA3A3",
        linewidth=0.65,
    )
    legend_title_y = 1.58
    legend_bar_y = 1.14
    legend_bar_height = 0.20
    axis.text(
        0,
        legend_title_y,
        "Configuration",
        ha="left",
        va="center",
        fontsize=7.8,
        fontweight="bold",
        color="#2A3032",
    )
    legend_cursor = 0.95
    for kind, label in (
        ("Features", "Features"),
        ("Embedding", "Embedding"),
        ("Graph", "Graph"),
    ):
        draw_output_icon(axis, legend_cursor, 1.03, 0.40, 0.40, kind, linewidth=0.68)
        axis.text(
            legend_cursor + 0.44,
            1.23,
            label,
            ha="left",
            va="center",
            fontsize=6.3,
            color="#4B5255",
        )
        legend_cursor += 1.22
    axis.text(
        0,
        0.80,
        "Features",
        ha="left",
        va="center",
        fontsize=6.4,
        fontweight="bold",
        color="#4B5255",
    )
    axis.text(0.75, 0.80, "HVG", ha="left", va="center", fontsize=6.4, color="#176B3A")
    axis.text(1.25, 0.80, "FULL", ha="left", va="center", fontsize=6.4, color="#63686B")
    axis.text(
        2.05,
        0.80,
        "Scaling",
        ha="left",
        va="center",
        fontsize=6.4,
        fontweight="bold",
        color="#4B5255",
    )
    axis.text(2.75, 0.80, "+ scaled", ha="left", va="center", fontsize=6.4, color="#4B5255")
    axis.text(3.65, 0.80, "- unscaled", ha="left", va="center", fontsize=6.4, color="#4B5255")
    for group in group_order:
        x_start, x_end = group_spans[group]
        gradient_start = x_start + 0.08
        gradient_end = x_end - 0.08
        strong, pale, _ = group_colors.get(group, fallback_colors)
        axis.text(
            x_start,
            legend_title_y,
            f"{group} rank",
            ha="left",
            va="center",
            fontsize=7.8,
            fontweight="bold",
            color="#2A3032",
        )
        segments = 40
        bar_width = (gradient_end - gradient_start) / segments
        for segment in range(segments):
            value = segment / (segments - 1)
            axis.add_patch(
                Rectangle(
                    (gradient_start + segment * bar_width, legend_bar_y),
                    bar_width + 0.002,
                    legend_bar_height,
                    facecolor=blend(strong, pale, value),
                    edgecolor="none",
                )
            )
        axis.add_patch(
            Rectangle(
                (gradient_start, legend_bar_y),
                gradient_end - gradient_start,
                legend_bar_height,
                facecolor="none",
                edgecolor="#6E7476",
                linewidth=0.4,
            )
        )
        lower_bound, upper_bound = rank_bounds[group]
        axis.text(
            gradient_start,
            0.94,
            f"{int(lower_bound)} best",
            ha="left",
            va="center",
            fontsize=5.8,
            color="#596166",
        )
        axis.text(
            gradient_end,
            0.94,
            f"{upper_bound:g} lower",
            ha="right",
            va="center",
            fontsize=5.8,
            color="#596166",
        )
    axis.text(
        0,
        0.34,
        "Bar length = score (0-1). Fill = source rank on a shared scale within each group. Numerals = top-three position among the displayed configurations; ties share a position. NA = not available.",
        ha="left",
        va="center",
        fontsize=6.2,
        color="#5C6366",
    )
    axis.text(
        0,
        0.10,
        "Data source: bundled scib_summary.csv. The unrelated local PDF was not used.",
        ha="left",
        va="center",
        fontsize=5.7,
        color="#7A8082",
    )
    output_path = BASE_DIR / "single_cell_benchmark_table_heatmap.png"
    figure.savefig(
        output_path,
        dpi=360,
        bbox_inches="tight",
        pad_inches=0.08,
        facecolor=figure.get_facecolor(),
        pil_kwargs={"compress_level": 6},
    )
    plt.close(figure)


if __name__ == "__main__":
    main()
