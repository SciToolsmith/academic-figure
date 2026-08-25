#!/usr/bin/env python3
"""Plot strictly paired observations across ordered conditions."""

from __future__ import annotations

import argparse
import csv
import math
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["svg.fonttype"] = "none"

import matplotlib.pyplot as plt
from matplotlib.colors import to_hex
import numpy as np


INCREASE_COLOR = "#147D78"
DECREASE_COLOR = "#C46B2D"
STABLE_COLOR = "#6B7280"
MAX_ERROR_DETAILS = 10


class DataContractError(ValueError):
    pass


@dataclass(frozen=True)
class Observation:
    subject_id: str
    condition: str
    value: float | None
    group: str
    source_row: int


@dataclass(frozen=True)
class PairedData:
    observations: tuple[Observation, ...]
    group_order: tuple[str, ...]
    condition_order: tuple[str, ...]
    has_group: bool
    raw_rows: int
    complete_subjects: int
    incomplete_subjects: int
    excluded_rows: int


def ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def parse_condition_order(text: str | None) -> tuple[str, ...] | None:
    if text is None:
        return None
    values = tuple(part.strip() for part in text.split(","))
    if any(not value for value in values):
        raise DataContractError("--condition-order contains an empty label")
    if len(values) != len(set(values)):
        raise DataContractError("--condition-order contains duplicate labels")
    return values


def read_input(
    path: Path,
    requested_order: tuple[str, ...] | None,
    incomplete_policy: str,
) -> PairedData:
    if not path.is_file():
        raise DataContractError(f"input file does not exist: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise DataContractError("input must contain a header row")
        fields = list(reader.fieldnames)
        if len(fields) != len(set(fields)):
            raise DataContractError("input contains duplicate column names")
        missing = [name for name in ("id", "condition", "value") if name not in fields]
        if missing:
            raise DataContractError("missing required column(s): " + ", ".join(missing))

        has_group = "group" in fields
        observations: list[Observation] = []
        errors: list[str] = []
        for row_number, row in enumerate(reader, start=2):
            subject_id = (row.get("id") or "").strip()
            condition = (row.get("condition") or "").strip()
            group = (row.get("group") or "").strip() if has_group else "All subjects"
            value_text = (row.get("value") or "").strip()
            row_errors: list[str] = []
            if not subject_id:
                row_errors.append("id is empty")
            if not condition:
                row_errors.append("condition is empty")
            if not group:
                row_errors.append("group is empty")

            value: float | None = None
            if value_text:
                try:
                    value = float(value_text)
                except ValueError:
                    row_errors.append(f"value is not numeric ({value_text!r})")
                else:
                    if not math.isfinite(value):
                        row_errors.append("value must be finite when supplied")

            if row_errors:
                if len(errors) < MAX_ERROR_DETAILS:
                    errors.append(f"row {row_number}: " + "; ".join(row_errors))
                continue
            observations.append(Observation(subject_id, condition, value, group, row_number))

    if errors:
        raise DataContractError(
            "input rows violate the data contract:\n  - " + "\n  - ".join(errors)
        )
    if not observations:
        raise DataContractError("input contains no observations")

    keys: dict[tuple[str, str, str], int] = {}
    duplicates: list[str] = []
    for item in observations:
        key = (item.group, item.subject_id, item.condition)
        if key in keys:
            if len(duplicates) < MAX_ERROR_DETAILS:
                duplicates.append(f"rows {keys[key]} and {item.source_row}: {key!r}")
        else:
            keys[key] = item.source_row
    if duplicates:
        raise DataContractError(
            "each (group, id, condition) must occur exactly once:\n  - "
            + "\n  - ".join(duplicates)
        )

    groups_by_id: dict[str, set[str]] = {}
    for item in observations:
        groups_by_id.setdefault(item.subject_id, set()).add(item.group)
    reassigned = [subject for subject, groups in groups_by_id.items() if len(groups) > 1]
    if reassigned:
        raise DataContractError(
            "each id must belong to one group; namespace reused IDs if needed: "
            + ", ".join(reassigned[:MAX_ERROR_DETAILS])
        )

    observed_conditions = ordered_unique(item.condition for item in observations)
    if len(observed_conditions) < 2:
        raise DataContractError("paired plotting requires at least two conditions")
    condition_order = requested_order or observed_conditions
    if set(condition_order) != set(observed_conditions) or len(condition_order) != len(observed_conditions):
        raise DataContractError(
            "--condition-order must contain every observed condition exactly once; observed: "
            + ", ".join(observed_conditions)
        )

    subject_keys = ordered_unique((item.group, item.subject_id) for item in observations)
    incomplete: list[tuple[tuple[str, str], tuple[str, ...], tuple[str, ...]]] = []
    complete_keys: set[tuple[str, str]] = set()
    for key in subject_keys:
        subject_rows = [item for item in observations if (item.group, item.subject_id) == key]
        present = {item.condition for item in subject_rows}
        absent = tuple(condition for condition in condition_order if condition not in present)
        missing_values = tuple(
            condition
            for condition in condition_order
            if any(item.condition == condition and item.value is None for item in subject_rows)
        )
        if absent or missing_values:
            incomplete.append((key, absent, missing_values))
        else:
            complete_keys.add(key)

    if incomplete and incomplete_policy == "error":
        details = []
        for (group, subject_id), absent, missing_values in incomplete[:MAX_ERROR_DETAILS]:
            parts = []
            if absent:
                parts.append("absent=" + ",".join(absent))
            if missing_values:
                parts.append("missing value=" + ",".join(missing_values))
            details.append(f"{group} / {subject_id}: " + "; ".join(parts))
        raise DataContractError(
            f"found {len(incomplete)} incomplete subject(s); default policy is error:\n  - "
            + "\n  - ".join(details)
            + "\nUse --incomplete-policy drop only after justifying complete-case exclusion."
        )

    kept = tuple(
        item
        for item in observations
        if (item.group, item.subject_id) in complete_keys and item.value is not None
    )
    if not kept:
        raise DataContractError("no complete subjects remain")
    group_order = ordered_unique(item.group for item in observations)
    for group in group_order:
        if not any(item.group == group for item in kept):
            raise DataContractError(f"group {group!r} has no complete subjects")

    return PairedData(
        observations=kept,
        group_order=group_order,
        condition_order=condition_order,
        has_group=has_group,
        raw_rows=len(observations),
        complete_subjects=len(complete_keys),
        incomplete_subjects=len(incomplete),
        excluded_rows=len(observations) - len(kept),
    )


def group_subjects(data: PairedData, group: str) -> tuple[str, ...]:
    return ordered_unique(
        item.subject_id for item in data.observations if item.group == group
    )


def value_lookup(data: PairedData) -> dict[tuple[str, str, str], float]:
    return {
        (item.group, item.subject_id, item.condition): float(item.value)
        for item in data.observations
    }


def direction(delta: float, tolerance: float) -> str:
    if delta > tolerance:
        return "increase"
    if delta < -tolerance:
        return "decrease"
    return "stable"


def transition_counts(
    data: PairedData,
    group: str,
    tolerance: float,
) -> list[tuple[str, str, int, int, int]]:
    lookup = value_lookup(data)
    subjects = group_subjects(data, group)
    results = []
    for first, second in zip(data.condition_order[:-1], data.condition_order[1:]):
        counts = {"increase": 0, "decrease": 0, "stable": 0}
        for subject_id in subjects:
            delta = lookup[group, subject_id, second] - lookup[group, subject_id, first]
            counts[direction(delta, tolerance)] += 1
        results.append((first, second, counts["increase"], counts["decrease"], counts["stable"]))
    return results


def condition_colors(conditions: Sequence[str]) -> dict[str, str]:
    cmap = matplotlib.colormaps["tab10" if len(conditions) <= 10 else "tab20"]
    return {condition: to_hex(cmap(index % cmap.N)) for index, condition in enumerate(conditions)}


def geometry(data: PairedData) -> tuple[int, int, float, float]:
    group_count = len(data.group_order)
    if group_count == 1:
        columns = 1
    elif group_count in (2, 3):
        columns = group_count
    elif group_count == 4:
        columns = 2
    else:
        columns = min(3, group_count)
    rows = math.ceil(group_count / columns)
    max_label = max(max(map(len, data.condition_order)), max(map(len, data.group_order)))
    proposed_width = 3.3 + 0.92 * len(data.condition_order) + 0.04 * max_label
    panel_width = (
        min(12.0, max(6.6, proposed_width))
        if group_count == 1
        else min(8.4, max(5.6, proposed_width))
    )
    panel_height = 5.0
    return rows, columns, panel_width * columns, panel_height * rows


def report(data: PairedData, tolerance: float) -> None:
    print(
        f"Loaded {data.raw_rows} rows: {data.complete_subjects} complete subject(s), "
        f"{data.incomplete_subjects} incomplete subject(s), {data.excluded_rows} row(s) excluded; "
        f"{len(data.condition_order)} condition(s), {len(data.group_order)} group(s)."
    )
    lookup = value_lookup(data)
    for group in data.group_order:
        subjects = group_subjects(data, group)
        print(f"group={group} | complete subjects={len(subjects)}")
        for condition in data.condition_order:
            values = np.asarray([lookup[group, subject, condition] for subject in subjects])
            q1, median, q3 = np.quantile(values, (0.25, 0.5, 0.75), method="linear")
            print(
                f"  condition={condition} | n={values.size} | q1={q1:.6g} | "
                f"median={median:.6g} | q3={q3:.6g}"
            )
        for first, second, increases, decreases, stable in transition_counts(data, group, tolerance):
            print(
                f"  transition={first} -> {second} | increase={increases} | "
                f"decrease={decreases} | within_tolerance={stable}"
            )


def draw(data: PairedData, title: str, y_label: str, tolerance: float) -> plt.Figure:
    rows, columns, width, height = geometry(data)
    figure, axes = plt.subplots(rows, columns, figsize=(width, height), squeeze=False, sharey=True)
    axes_flat = axes.ravel()
    lookup = value_lookup(data)
    colors = condition_colors(data.condition_order)
    positions = np.arange(len(data.condition_order), dtype=float)
    all_values = np.asarray([float(item.value) for item in data.observations])
    data_min, data_max = float(np.min(all_values)), float(np.max(all_values))
    span = max(data_max - data_min, max(abs(data_min), abs(data_max), 1.0) * 0.2)
    y_limits = (data_min - 0.10 * span, data_max + 0.27 * span)
    annotation_y = data_max + 0.13 * span

    for panel_index, group in enumerate(data.group_order):
        axis = axes_flat[panel_index]
        subjects = group_subjects(data, group)
        offsets = dict(
            zip(sorted(subjects), np.linspace(-0.12, 0.12, len(subjects)) if len(subjects) > 1 else [0.0])
        )
        arrays = [
            np.asarray([lookup[group, subject, condition] for subject in subjects])
            for condition in data.condition_order
        ]
        boxes = axis.boxplot(
            arrays,
            positions=positions,
            widths=0.48,
            patch_artist=True,
            showfliers=False,
            whis=1.5,
            boxprops={"edgecolor": "#59636C", "linewidth": 1.0},
            medianprops={"color": "#20262C", "linewidth": 1.5},
            whiskerprops={"color": "#7B858E", "linewidth": 0.9},
            capprops={"color": "#7B858E", "linewidth": 0.9},
            zorder=1,
        )
        for patch, condition in zip(boxes["boxes"], data.condition_order):
            patch.set_facecolor(colors[condition])
            patch.set_alpha(0.16)

        for subject in subjects:
            subject_values = [lookup[group, subject, condition] for condition in data.condition_order]
            subject_x = positions + offsets[subject]
            for index in range(len(data.condition_order) - 1):
                delta = subject_values[index + 1] - subject_values[index]
                status = direction(delta, tolerance)
                line_color = {
                    "increase": INCREASE_COLOR,
                    "decrease": DECREASE_COLOR,
                    "stable": STABLE_COLOR,
                }[status]
                axis.plot(
                    subject_x[index : index + 2],
                    subject_values[index : index + 2],
                    color=line_color,
                    linewidth=0.75 if len(subjects) <= 150 else 0.45,
                    alpha=0.46 if len(subjects) <= 150 else 0.25,
                    zorder=2,
                )
            for x_value, y_value, condition in zip(subject_x, subject_values, data.condition_order):
                axis.scatter(
                    x_value,
                    y_value,
                    s=22 if len(subjects) <= 150 else 10,
                    color=colors[condition],
                    edgecolor="white",
                    linewidth=0.35,
                    alpha=0.88,
                    rasterized=len(subjects) > 1500,
                    zorder=3,
                )

        if len(data.condition_order) <= 6:
            for index, (_, _, increases, decreases, stable) in enumerate(
                transition_counts(data, group, tolerance)
            ):
                axis.text(
                    index + 0.5,
                    annotation_y,
                    f"↑{increases}  ↓{decreases}  ={stable}",
                    ha="center",
                    va="center",
                    fontsize=7.5,
                    color="#4C5560",
                )

        tick_labels = [
            textwrap.fill(condition, width=15) + f"\n(n={len(subjects)})"
            for condition in data.condition_order
        ]
        axis.set_xticks(positions, labels=tick_labels, fontsize=8.2)
        axis.tick_params(axis="x", length=0, pad=7)
        axis.tick_params(axis="y", labelsize=8.3, colors="#4A525B")
        axis.set_xlim(-0.55, len(data.condition_order) - 0.45)
        axis.set_ylim(y_limits)
        axis.grid(axis="y", color="#E5E9ED", linewidth=0.65)
        axis.set_axisbelow(True)
        for side in ("top", "right"):
            axis.spines[side].set_visible(False)
        axis.spines["left"].set_color("#77818A")
        axis.spines["bottom"].set_color("#77818A")
        if data.has_group:
            axis.set_title(
                f"{group} · n={len(subjects)} complete subjects",
                loc="left",
                fontsize=10.5,
                fontweight="semibold",
                pad=8,
            )

    for axis in axes_flat[len(data.group_order) :]:
        axis.set_visible(False)

    subtitle = (
        f"{data.complete_subjects} complete subjects · {len(data.condition_order)} ordered conditions · "
        f"{len(data.group_order)} group{'s' if len(data.group_order) != 1 else ''}"
    )
    if data.incomplete_subjects:
        subtitle += f" · dropped {data.incomplete_subjects} incomplete subjects"
    figure.suptitle(title, x=0.035, y=0.988, ha="left", fontsize=15, fontweight="semibold")
    figure.text(0.035, 0.952, subtitle, ha="left", va="top", fontsize=9, color="#59616B")
    figure.supylabel(y_label, x=0.010, fontsize=10)
    figure.text(
        0.035,
        0.012,
        f"Lines join the same ID. Segment direction: teal ↑, orange ↓, gray within ±{tolerance:g}. "
        "Boxes show Q1–Q3, median and 1.5×IQR whiskers; no inferential test is performed.",
        ha="left",
        va="bottom",
        fontsize=7.4,
        color="#66707A",
    )
    figure.tight_layout(rect=(0.025, 0.075, 0.995, 0.915), h_pad=1.5, w_pad=1.8)
    return figure


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot complete paired trajectories across conditions.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-prefix", required=True, type=Path)
    parser.add_argument("--title", default="Paired change across conditions")
    parser.add_argument("--y-label", default="Value")
    parser.add_argument("--condition-order", default=None, help="Comma-separated complete order")
    parser.add_argument(
        "--incomplete-policy",
        choices=("error", "drop"),
        default="error",
        help="Default error prevents silent complete-case analysis",
    )
    parser.add_argument(
        "--change-tolerance",
        type=float,
        default=0.0,
        help="Absolute value-unit tolerance for the neutral direction class",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output_prefix.suffix.lower() in {".png", ".svg"}:
        print("ERROR: --output-prefix must not include .png or .svg", file=sys.stderr)
        return 2
    if not math.isfinite(args.change_tolerance) or args.change_tolerance < 0:
        print("ERROR: --change-tolerance must be a finite non-negative number", file=sys.stderr)
        return 2
    try:
        requested_order = parse_condition_order(args.condition_order)
        data = read_input(args.input, requested_order, args.incomplete_policy)
    except DataContractError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    figure = draw(data, args.title, args.y_label, args.change_tolerance)
    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
    png_path = Path(f"{args.output_prefix}.png")
    svg_path = Path(f"{args.output_prefix}.svg")
    figure.savefig(png_path, dpi=320, facecolor="white", bbox_inches="tight")
    figure.savefig(svg_path, facecolor="white", bbox_inches="tight")
    plt.close(figure)
    report(data, args.change_tolerance)
    print(f"Wrote {png_path}")
    print(f"Wrote {svg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
