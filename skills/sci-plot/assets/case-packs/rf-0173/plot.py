from pathlib import Path
import csv
import numpy as np
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import wilcoxon

base = Path(__file__).resolve().parent

groups_a = ["intra-primary", "intra-met", "inter-met", "primary-met"]
labels_a = ["Intra-primary", "Intra-met", "Inter-met", "Primary-met"]
colors_a = ["#355C7D", "#12664F", "#2A9D62", "#209DB5"]
comparisons_a = [
    ("intra-primary", "intra-met"),
    ("intra-met", "inter-met"),
    ("intra-primary", "inter-met"),
    ("inter-met", "primary-met"),
    ("intra-primary", "primary-met"),
]
types_b = [
    "Plasma",
    "CD27+ effector B",
    "CD27- effector B",
    "CD95 memory B",
    "Core memory B",
    "Type 2 polarized memory B",
]
ages_b = ["Young", "Older"]
days_b = ["Day 0", "Day 7"]
colors_b = {"Young": "#228C82", "Older": "#C98324"}

def read_rows(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))

def bh_adjust(values):
    array = np.asarray(values, dtype=float)
    order = np.argsort(array, kind="mergesort")
    ranked = array[order]
    adjusted = ranked * len(array) / np.arange(1, len(array) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    result = np.empty_like(adjusted)
    result[order] = np.clip(adjusted, 0, 1)
    return result

def exact_paired(x, y):
    return float(
        wilcoxon(
            np.asarray(x, dtype=float),
            np.asarray(y, dtype=float),
            alternative="two-sided",
            zero_method="wilcox",
            correction=False,
            method="exact",
        ).pvalue
    )

def format_probability(value):
    if value < 0.001:
        return f"{value:.2e}"
    return f"{value:.4f}"

def add_boxplots(axis, arrays, positions, colors, width=0.54):
    result = axis.boxplot(
        arrays,
        positions=positions,
        widths=width,
        patch_artist=True,
        showfliers=False,
        whis=1.5,
        boxprops={"edgecolor": "#66737A", "linewidth": 1.25},
        medianprops={"color": "#1C2930", "linewidth": 1.8},
        whiskerprops={"color": "#849097", "linewidth": 1.1},
        capprops={"color": "#849097", "linewidth": 1.1},
    )
    for patch, color in zip(result["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.18)

rows_a = read_rows(base / "data1.csv")
if list(rows_a[0]) != ["id", "variable", "value"] or len(rows_a) != 96:
    raise ValueError("Unexpected data1.csv schema or row count")
if {row["variable"] for row in rows_a} != set(groups_a):
    raise ValueError("Unexpected mutation-diversity group")
keys_a = [(row["id"], row["variable"]) for row in rows_a]
if len(keys_a) != len(set(keys_a)):
    raise ValueError("Duplicate data1 patient-group key")
if any(not row["id"] or not row["variable"] for row in rows_a):
    raise ValueError("Missing data1 identifier")
lookup_a = {
    (row["id"], row["variable"]): float(row["value"])
    for row in rows_a
    if row["value"] != ""
}
ids_a = sorted({row["id"] for row in rows_a})
missing_a = sum(row["value"] == "" for row in rows_a)
if missing_a != 5:
    raise ValueError("Unexpected data1 missing-value count")

tests_a = []
for first, second in comparisons_a:
    paired_ids = sorted(
        {patient for patient, group in lookup_a if group == first}
        & {patient for patient, group in lookup_a if group == second}
    )
    first_values = np.asarray([lookup_a[patient, first] for patient in paired_ids])
    second_values = np.asarray([lookup_a[patient, second] for patient in paired_ids])
    tests_a.append(
        {
            "first": first,
            "second": second,
            "n": len(paired_ids),
            "p": exact_paired(first_values, second_values),
            "delta": float(np.median(second_values - first_values)),
        }
    )
for test, q_value in zip(tests_a, bh_adjust([test["p"] for test in tests_a])):
    test["q"] = float(q_value)

rows_b = read_rows(base / "data2.csv")
if list(rows_b[0]) != ["ID", "Age", "Day", "Type", "Value"] or len(rows_b) != 814:
    raise ValueError("Unexpected data2.csv schema or row count")
if {row["Age"] for row in rows_b} != set(ages_b):
    raise ValueError("Unexpected age group")
if {row["Day"] for row in rows_b} != set(days_b):
    raise ValueError("Unexpected study day")
if {row["Type"] for row in rows_b} != set(types_b):
    raise ValueError("Unexpected B-cell type")
if any("" in row.values() for row in rows_b):
    raise ValueError("Missing data2 value")
keys_b = [(row["ID"], row["Age"], row["Day"], row["Type"]) for row in rows_b]
if len(keys_b) != len(set(keys_b)):
    raise ValueError("Duplicate data2 patient-age-day-type key")
age_by_id = {}
for row in rows_b:
    age_by_id.setdefault(row["ID"], set()).add(row["Age"])
if any(len(values) != 1 for values in age_by_id.values()):
    raise ValueError("Patient assigned to multiple age groups")
lookup_b = {
    (row["ID"], row["Age"], row["Day"], row["Type"]): float(row["Value"])
    for row in rows_b
}

tests_b = []
for cell_type in types_b:
    for age in ages_b:
        paired_ids = sorted(
            {
                patient
                for patient, row_age, day, row_type in lookup_b
                if row_age == age and day == "Day 0" and row_type == cell_type
            }
            & {
                patient
                for patient, row_age, day, row_type in lookup_b
                if row_age == age and day == "Day 7" and row_type == cell_type
            }
        )
        day0 = np.asarray(
            [lookup_b[patient, age, "Day 0", cell_type] for patient in paired_ids]
        )
        day7 = np.asarray(
            [lookup_b[patient, age, "Day 7", cell_type] for patient in paired_ids]
        )
        tests_b.append(
            {
                "type": cell_type,
                "age": age,
                "ids": paired_ids,
                "day0": day0,
                "day7": day7,
                "n": len(paired_ids),
                "p": exact_paired(day0, day7),
            }
        )
for test, q_value in zip(tests_b, bh_adjust([test["p"] for test in tests_b])):
    test["q"] = float(q_value)

mpl.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9.5,
        "axes.edgecolor": "#7D8A91",
        "axes.linewidth": 0.8,
        "xtick.color": "#31414A",
        "ytick.color": "#31414A",
        "text.color": "#17242C",
        "figure.facecolor": "#F5F7F5",
        "axes.facecolor": "#FFFFFF",
        "savefig.facecolor": "#F5F7F5",
    }
)

figure = plt.figure(figsize=(18, 13))
outer = figure.add_gridspec(
    2,
    1,
    height_ratios=[0.88, 1.48],
    left=0.07,
    right=0.97,
    bottom=0.13,
    top=0.86,
    hspace=0.40,
)
top = outer[0].subgridspec(1, 2, width_ratios=[1.36, 0.76], wspace=0.14)
axis_a = figure.add_subplot(top[0, 0])
axis_table = figure.add_subplot(top[0, 1])
bottom = outer[1].subgridspec(2, 3, hspace=0.55, wspace=0.22)
axes_b = [figure.add_subplot(bottom[index // 3, index % 3]) for index in range(6)]

figure.text(
    0.07,
    0.965,
    "Paired within-patient profiles across diversity and immune-cell states",
    ha="left",
    va="top",
    fontsize=22,
    fontweight="bold",
)
figure.text(
    0.07,
    0.932,
    "Raw observations, paired trajectories and distribution summaries",
    ha="left",
    va="top",
    fontsize=11,
    color="#5B6A72",
)

offset_a = {
    patient: value
    for patient, value in zip(ids_a, np.linspace(-0.14, 0.14, len(ids_a)))
}
for patient in ids_a:
    for index in range(len(groups_a) - 1):
        first = groups_a[index]
        second = groups_a[index + 1]
        if (patient, first) in lookup_a and (patient, second) in lookup_a:
            axis_a.plot(
                [index + offset_a[patient], index + 1 + offset_a[patient]],
                [lookup_a[patient, first], lookup_a[patient, second]],
                color="#8D989D",
                linewidth=0.75,
                alpha=0.62,
                zorder=1,
            )
arrays_a = [
    np.asarray([lookup_a[patient, group] for patient in ids_a if (patient, group) in lookup_a])
    for group in groups_a
]
add_boxplots(axis_a, arrays_a, np.arange(4), colors_a, width=0.58)
for index, group in enumerate(groups_a):
    patients = [patient for patient in ids_a if (patient, group) in lookup_a]
    axis_a.scatter(
        [index + offset_a[patient] for patient in patients],
        [lookup_a[patient, group] for patient in patients],
        s=34,
        color=colors_a[index],
        edgecolor="#FFFFFF",
        linewidth=0.45,
        zorder=4,
    )
axis_a.set_xlim(-0.55, 3.55)
axis_a.set_ylim(-0.035, 1.02)
axis_a.set_xticks(range(4))
axis_a.set_xticklabels(
    [f"{label}\n(n={len(values)})" for label, values in zip(labels_a, arrays_a)]
)
axis_a.set_ylabel("Mean mutation diversity per patient")
axis_a.grid(axis="y", color="#DDE4E1", linewidth=0.7)
axis_a.spines[["top", "right"]].set_visible(False)
axis_a.set_title(
    "A   Mutation diversity",
    loc="left",
    fontsize=14,
    fontweight="bold",
    pad=23,
)
axis_a.text(
    0,
    1.025,
    "24 supplied patient IDs; 5 missing values retained as missing",
    transform=axis_a.transAxes,
    ha="left",
    va="bottom",
    fontsize=9.3,
    color="#5B6A72",
)

axis_table.set_xlim(0, 1)
axis_table.set_ylim(0, 1)
axis_table.axis("off")
axis_table.text(
    0,
    1.08,
    "Displayed paired comparisons",
    ha="left",
    va="bottom",
    fontsize=13,
    fontweight="bold",
)
axis_table.text(
    0,
    1.015,
    "Complete common IDs per row",
    ha="left",
    va="bottom",
    fontsize=9.2,
    color="#5B6A72",
)
headers = ["Comparison", "n", "Median Δ", "raw p", "BH q"]
columns = [0.0, 0.50, 0.69, 0.84, 0.98]
for x_value, header in zip(columns, headers):
    axis_table.text(
        x_value,
        0.91,
        header,
        ha="left" if header == "Comparison" else "right",
        va="center",
        fontsize=8.6,
        fontweight="bold",
        color="#3B4B54",
    )
axis_table.plot([0, 0.98], [0.865, 0.865], color="#9AA6AB", linewidth=0.9)
short_labels = {
    "intra-primary": "Intra-primary",
    "intra-met": "Intra-met",
    "inter-met": "Inter-met",
    "primary-met": "Primary-met",
}
for index, test in enumerate(tests_a):
    y_value = 0.77 - index * 0.145
    if index % 2 == 0:
        axis_table.axhspan(y_value - 0.064, y_value + 0.064, color="#EAF0ED", zorder=0)
    values = [
        f"{short_labels[test['first']]} → {short_labels[test['second']]}",
        str(test["n"]),
        f"{test['delta']:+.3f}",
        format_probability(test["p"]),
        format_probability(test["q"]),
    ]
    for x_value, value in zip(columns, values):
        axis_table.text(
            x_value,
            y_value,
            value,
            ha="left" if x_value == 0 else "right",
            va="center",
            fontsize=8.4,
            fontweight="bold" if x_value == 0.94 and test["q"] < 0.05 else "normal",
            color="#17242C",
        )
axis_table.text(
    0,
    -0.02,
    "Δ = median(second − first)",
    ha="left",
    va="bottom",
    fontsize=8.3,
    color="#5B6A72",
)

figure.text(
    0.07,
    0.565,
    "B   B-cell frequency change from Day 0 to Day 7",
    ha="left",
    va="bottom",
    fontsize=14,
    fontweight="bold",
)
figure.text(
    0.07,
    0.545,
    "Pairing is performed separately by patient ID within each age group",
    ha="left",
    va="bottom",
    fontsize=9.3,
    color="#5B6A72",
)

positions_b = [0, 1, 2.65, 3.65]
for axis, cell_type in zip(axes_b, types_b):
    type_tests = {
        test["age"]: test for test in tests_b if test["type"] == cell_type
    }
    arrays = []
    panel_values = []
    for age in ages_b:
        test = type_tests[age]
        arrays.extend([test["day0"], test["day7"]])
        panel_values.extend(test["day0"])
        panel_values.extend(test["day7"])
        offsets = {
            patient: value
            for patient, value in zip(
                test["ids"], np.linspace(-0.12, 0.12, len(test["ids"]))
            )
        }
        base_position = 0 if age == "Young" else 2.65
        for patient, first_value, second_value in zip(
            test["ids"], test["day0"], test["day7"]
        ):
            axis.plot(
                [
                    base_position + offsets[patient],
                    base_position + 1 + offsets[patient],
                ],
                [first_value, second_value],
                color="#879399",
                linewidth=0.55,
                alpha=0.62,
                zorder=1,
            )
            axis.scatter(
                [
                    base_position + offsets[patient],
                    base_position + 1 + offsets[patient],
                ],
                [first_value, second_value],
                s=12,
                color=colors_b[age],
                edgecolor="#FFFFFF",
                linewidth=0.25,
                zorder=4,
            )
    add_boxplots(
        axis,
        arrays,
        positions_b,
        [colors_b["Young"], colors_b["Young"], colors_b["Older"], colors_b["Older"]],
        width=0.52,
    )
    panel_values = np.asarray(panel_values)
    span = max(float(np.ptp(panel_values)), 0.8)
    lower = float(panel_values.min()) - span * 0.08
    upper = float(panel_values.max()) + span * 0.28
    axis.set_ylim(lower, upper)
    axis.set_xlim(-0.55, 4.2)
    axis.set_xticks(positions_b)
    axis.set_xticklabels(["Day 0\nYoung", "Day 7\nYoung", "Day 0\nOlder", "Day 7\nOlder"], fontsize=7.7)
    axis.grid(axis="y", color="#E1E7E4", linewidth=0.6)
    axis.spines[["top", "right"]].set_visible(False)
    axis.set_title(cell_type, loc="left", fontsize=10.2, fontweight="bold", pad=5)
    young = type_tests["Young"]
    older = type_tests["Older"]
    axis.text(
        0.02,
        0.98,
        f"Young n={young['n']}  p={format_probability(young['p'])}  q={format_probability(young['q'])}",
        transform=axis.transAxes,
        ha="left",
        va="top",
        fontsize=7.25,
        color=colors_b["Young"],
        fontweight="bold",
    )
    axis.text(
        0.02,
        0.895,
        f"Older n={older['n']}  p={format_probability(older['p'])}  q={format_probability(older['q'])}",
        transform=axis.transAxes,
        ha="left",
        va="top",
        fontsize=7.25,
        color=colors_b["Older"],
        fontweight="bold",
    )
    if axis in [axes_b[0], axes_b[3]]:
        axis.set_ylabel("Frequency (CLR)")

caption = (
    "Supplied: patient IDs, group/time labels and observed values. Derived: box summaries, paired median changes, p values and BH q values.\n"
    "Tests are two-sided exact paired Wilcoxon tests; raw p and BH q are shown, with correction applied separately across A (5 comparisons) and B (12 comparisons).\n"
    "Panel A uses complete common IDs for each comparison. Panel B Plasma/Young lacks BR1023 at both days (n = 25); all other Young tests use n = 26 and Older tests use n = 42. No between-age tests were performed."
)
figure.text(
    0.07,
    0.045,
    caption,
    ha="left",
    va="bottom",
    fontsize=8.15,
    color="#506069",
    linespacing=1.45,
)
figure.savefig(base / "plot_python.png", dpi=360)
plt.close(figure)
