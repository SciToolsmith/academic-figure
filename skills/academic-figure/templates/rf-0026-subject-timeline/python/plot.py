#!/usr/bin/env python3
"""Render a validated subject timeline as PNG and SVG."""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import MaxNLocator


TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = TEMPLATE_ROOT / "data"
PAGE_LIMIT = 36
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
INTEGER_RE = re.compile(r"^[0-9]+$")
MARKERS = {
    "circle": "o",
    "diamond": "D",
    "triangle": "^",
    "square": "s",
    "cross": "x",
}


class ValidationError(Exception):
    """Raised when an input violates the plotting contract."""


def fail(problems: Iterable[str]) -> None:
    items = list(problems)
    if items:
        shown = items[:25]
        suffix = "\n  - ... additional errors omitted" if len(items) > 25 else ""
        raise ValidationError("Input validation failed:\n  - " + "\n  - ".join(shown) + suffix)


def read_csv_table(
    path: Path,
    name: str,
    required: Sequence[str],
    allow_empty: bool = False,
) -> Tuple[List[Dict[str, str]], List[str]]:
    if not path.is_file():
        raise ValidationError("{} file not found: {}".format(name, path))
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames
            if headers is None:
                raise ValidationError("{} has no CSV header: {}".format(name, path))
            header_problems: List[str] = []
            if any(header is None or header.strip() == "" for header in headers):
                header_problems.append("{} contains an empty column name".format(name))
            if len(set(headers)) != len(headers):
                header_problems.append("{} contains duplicate column names".format(name))
            missing = [column for column in required if column not in headers]
            if missing:
                header_problems.append(
                    "{} is missing required columns: {}".format(name, ", ".join(missing))
                )
            fail(header_problems)
            rows: List[Dict[str, str]] = []
            for line_number, row in enumerate(reader, start=2):
                if None in row:
                    raise ValidationError(
                        "{} line {} has more values than header columns".format(name, line_number)
                    )
                clean = {key: (value or "").strip() for key, value in row.items()}
                clean["__line__"] = str(line_number)
                rows.append(clean)
    except UnicodeDecodeError as exc:
        raise ValidationError("{} must be UTF-8 CSV: {}".format(name, exc)) from exc
    if not rows and not allow_empty:
        raise ValidationError("{} must contain at least one data row".format(name))
    return rows, list(headers)


def parse_finite(value: str, context: str, problems: List[str]) -> Optional[float]:
    try:
        number = float(value)
    except ValueError:
        problems.append("{} must be numeric; got {!r}".format(context, value))
        return None
    if not math.isfinite(number):
        problems.append("{} must be finite; got {!r}".format(context, value))
        return None
    return number


def validate_metadata(tables: Sequence[Tuple[str, List[Dict[str, str]], List[str]]]) -> None:
    problems: List[str] = []
    declared: List[Tuple[str, Tuple[str, str]]] = []
    for name, rows, headers in tables:
        has_status = "data_status" in headers
        has_seed = "simulation_seed" in headers
        if has_status != has_seed:
            problems.append(
                "{} must provide data_status and simulation_seed together".format(name)
            )
            continue
        if not has_status:
            continue
        pairs = {(row["data_status"], row["simulation_seed"]) for row in rows}
        if any(not status or not seed for status, seed in pairs):
            problems.append("{} has empty simulation provenance values".format(name))
        if len(pairs) != 1:
            problems.append("{} has inconsistent simulation provenance values".format(name))
        elif pairs:
            declared.append((name, next(iter(pairs))))
    if declared:
        expected = declared[0][1]
        for name, pair in declared[1:]:
            if pair != expected:
                problems.append(
                    "{} provenance {} does not match {} provenance {}".format(
                        name, pair, declared[0][0], expected
                    )
                )
    fail(problems)


def validate_type_styles(
    rows: List[Dict[str, str]], type_column: str, label_column: str, name: str
) -> Dict[str, Dict[str, str]]:
    problems: List[str] = []
    result: Dict[str, Dict[str, str]] = {}
    for row in rows:
        line = row["__line__"]
        key = row[type_column]
        if not key:
            problems.append("{} line {} has an empty {}".format(name, line, type_column))
        elif key in result:
            problems.append("{} line {} duplicates type {!r}".format(name, line, key))
        label = row[label_column]
        if not label:
            problems.append("{} line {} has an empty legend label".format(name, line))
        color = row["color"]
        if not COLOR_RE.fullmatch(color):
            problems.append(
                "{} line {} color must be #RRGGBB; got {!r}".format(name, line, color)
            )
        if key and key not in result:
            result[key] = row
    fail(problems)
    return result


def validate_subjects(rows: List[Dict[str, str]]) -> Tuple[List[Dict[str, object]], str]:
    problems: List[str] = []
    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    parsed: List[Dict[str, object]] = []
    for row in rows:
        line = row["__line__"]
        subject_id = row["subject_id"]
        if not subject_id:
            problems.append("subjects line {} has an empty subject_id".format(line))
        elif subject_id in seen_ids:
            problems.append("subjects line {} duplicates subject_id {!r}".format(line, subject_id))
        else:
            seen_ids.add(subject_id)
        if not row["subject_label"]:
            problems.append("subjects line {} has an empty subject_label".format(line))
        order: Optional[int] = None
        if not INTEGER_RE.fullmatch(row["display_order"]):
            problems.append("subjects line {} display_order must be a positive integer".format(line))
        else:
            order = int(row["display_order"])
            if order < 1:
                problems.append("subjects line {} display_order must be positive".format(line))
            elif order in seen_orders:
                problems.append("subjects line {} duplicates display_order {}".format(line, order))
            else:
                seen_orders.add(order)
        start = parse_finite(row["observation_start"], "subjects line {} observation_start".format(line), problems)
        end = parse_finite(row["observation_end"], "subjects line {} observation_end".format(line), problems)
        if start is not None and end is not None and not start < end:
            problems.append("subjects line {} requires observation_start < observation_end".format(line))
        if not row["time_unit"]:
            problems.append("subjects line {} has an empty time_unit".format(line))
        parsed.append(
            {
                "subject_id": subject_id,
                "subject_label": row["subject_label"],
                "display_order": order,
                "observation_start": start,
                "observation_end": end,
                "time_unit": row["time_unit"],
            }
        )
    units = {str(row["time_unit"]) for row in parsed if row["time_unit"]}
    if len(units) != 1:
        problems.append("subjects must use exactly one non-empty time_unit; found {}".format(sorted(units)))
    fail(problems)
    parsed.sort(key=lambda row: int(row["display_order"]))
    return parsed, next(iter(units))


def validate_intervals(
    rows: List[Dict[str, str]],
    subjects: Sequence[Dict[str, object]],
    styles: Mapping[str, Dict[str, str]],
    unit: str,
) -> List[Dict[str, object]]:
    subject_map = {str(row["subject_id"]): row for row in subjects}
    problems: List[str] = []
    seen_ids: set[str] = set()
    last_start: Dict[str, float] = {}
    last_end: Dict[str, float] = {}
    counts: Dict[str, int] = {subject_id: 0 for subject_id in subject_map}
    parsed: List[Dict[str, object]] = []
    for row in rows:
        line = row["__line__"]
        interval_id = row["interval_id"]
        subject_id = row["subject_id"]
        if not interval_id:
            problems.append("intervals line {} has an empty interval_id".format(line))
        elif interval_id in seen_ids:
            problems.append("intervals line {} duplicates interval_id {!r}".format(line, interval_id))
        else:
            seen_ids.add(interval_id)
        subject = subject_map.get(subject_id)
        if not subject_id:
            problems.append("intervals line {} has an empty subject_id".format(line))
        elif subject is None:
            problems.append("intervals line {} references unknown subject_id {!r}".format(line, subject_id))
        interval_type = row["interval_type"]
        if interval_type not in styles:
            problems.append("intervals line {} uses unknown interval_type {!r}".format(line, interval_type))
        if row["time_unit"] != unit:
            problems.append(
                "intervals line {} time_unit {!r} does not equal {!r}".format(line, row["time_unit"], unit)
            )
        start = parse_finite(row["start"], "intervals line {} start".format(line), problems)
        end = parse_finite(row["end"], "intervals line {} end".format(line), problems)
        if start is not None and end is not None:
            if not start < end:
                problems.append("intervals line {} requires start < end".format(line))
            if subject is not None:
                lower = float(subject["observation_start"])
                upper = float(subject["observation_end"])
                if start < lower or end > upper:
                    problems.append(
                        "intervals line {} [{}, {}] lies outside subject {} observation [{}, {}]".format(
                            line, start, end, subject_id, lower, upper
                        )
                    )
                if subject_id in last_start and start < last_start[subject_id]:
                    problems.append(
                        "intervals line {} is out of start-time order for subject {}".format(line, subject_id)
                    )
                if subject_id in last_end and start < last_end[subject_id]:
                    problems.append(
                        "intervals line {} overlaps the preceding interval for subject {}".format(line, subject_id)
                    )
                last_start[subject_id] = start
                last_end[subject_id] = end
                counts[subject_id] += 1
        parsed.append(
            {
                "interval_id": interval_id,
                "subject_id": subject_id,
                "start": start,
                "end": end,
                "interval_type": interval_type,
            }
        )
    for subject_id, count in counts.items():
        if count == 0:
            problems.append("subject {!r} has no valid interval row".format(subject_id))
    fail(problems)
    return parsed


def validate_events(
    rows: List[Dict[str, str]],
    subjects: Sequence[Dict[str, object]],
    styles: Mapping[str, Dict[str, str]],
    unit: str,
) -> List[Dict[str, object]]:
    subject_map = {str(row["subject_id"]): row for row in subjects}
    problems: List[str] = []
    seen_ids: set[str] = set()
    last_time: Dict[str, float] = {}
    parsed: List[Dict[str, object]] = []
    for row in rows:
        line = row["__line__"]
        event_id = row["event_id"]
        subject_id = row["subject_id"]
        if not event_id:
            problems.append("events line {} has an empty event_id".format(line))
        elif event_id in seen_ids:
            problems.append("events line {} duplicates event_id {!r}".format(line, event_id))
        else:
            seen_ids.add(event_id)
        subject = subject_map.get(subject_id)
        if not subject_id:
            problems.append("events line {} has an empty subject_id".format(line))
        elif subject is None:
            problems.append("events line {} references unknown subject_id {!r}".format(line, subject_id))
        event_type = row["event_type"]
        if event_type not in styles:
            problems.append(
                "events line {} uses unknown event_type {!r}; no fallback mapping is allowed".format(
                    line, event_type
                )
            )
        if row["time_unit"] != unit:
            problems.append(
                "events line {} time_unit {!r} does not equal {!r}".format(line, row["time_unit"], unit)
            )
        time = parse_finite(row["time"], "events line {} time".format(line), problems)
        if time is not None and subject is not None:
            lower = float(subject["observation_start"])
            upper = float(subject["observation_end"])
            if time < lower or time > upper:
                problems.append(
                    "events line {} time {} lies outside subject {} observation [{}, {}]".format(
                        line, time, subject_id, lower, upper
                    )
                )
            if subject_id in last_time and time < last_time[subject_id]:
                problems.append(
                    "events line {} is out of time order for subject {}".format(line, subject_id)
                )
            last_time[subject_id] = time
        parsed.append(
            {
                "event_id": event_id,
                "subject_id": subject_id,
                "time": time,
                "event_type": event_type,
            }
        )
    fail(problems)
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and draw a non-causal subject interval timeline."
    )
    parser.add_argument("--subjects", type=Path, default=DATA_DIR / "simulated_fixed_seed_subjects.csv")
    parser.add_argument("--intervals", type=Path, default=DATA_DIR / "simulated_fixed_seed_intervals.csv")
    parser.add_argument("--events", type=Path)
    parser.add_argument("--interval-styles", type=Path, default=DATA_DIR / "interval_types.csv")
    parser.add_argument("--event-styles", type=Path)
    parser.add_argument("--output-prefix", type=Path, required=True)
    parser.add_argument("--title", default="Subject timelines")
    parser.add_argument("--dpi", type=int, default=320)
    return parser


def render(
    subjects: Sequence[Dict[str, object]],
    intervals: Sequence[Dict[str, object]],
    events: Sequence[Dict[str, object]],
    interval_styles: Mapping[str, Dict[str, str]],
    event_styles: Mapping[str, Dict[str, str]],
    unit: str,
    output_prefix: Path,
    title: str,
    dpi: int,
) -> Tuple[Path, Path]:
    n_subjects = len(subjects)
    if n_subjects > PAGE_LIMIT:
        raise ValidationError(
            "Single-page limit is {} subjects; received {}. Split the validated dataset "
            "upstream into contiguous display_order batches or declared scientific groups, "
            "then run each complete batch separately. Automatic pagination and truncation are disabled.".format(
                PAGE_LIMIT, n_subjects
            )
        )
    subject_labels = ["{} [{}]".format(row["subject_label"], row["subject_id"]) for row in subjects]
    legend_labels = [row["interval_type_label"] for row in interval_styles.values()]
    legend_labels.extend(row["event_type_label"] for row in event_styles.values())
    max_subject_chars = max(len(label) for label in subject_labels)
    max_legend_chars = max([len(label) for label in legend_labels] or [0])
    legend_count = max(1, len(legend_labels))
    legend_columns = min(4, legend_count)
    legend_rows = int(math.ceil(legend_count / legend_columns))
    width = min(17.0, max(10.0, 9.0 + 0.055 * max_subject_chars + 0.025 * max_legend_chars))
    height = max(5.4, 3.4 + 0.38 * n_subjects + 0.35 * legend_rows)

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 13,
            "axes.labelsize": 10,
            "legend.fontsize": 8.5,
            "svg.fonttype": "none",
        }
    )
    fig, ax = plt.subplots(figsize=(width, height))
    y_by_subject = {str(row["subject_id"]): index for index, row in enumerate(subjects)}
    xmin = min(float(row["observation_start"]) for row in subjects)
    xmax = max(float(row["observation_end"]) for row in subjects)
    span = xmax - xmin
    pad = max(span * 0.025, 0.1)

    for y, subject in enumerate(subjects):
        if y % 2 == 0:
            ax.axhspan(y - 0.48, y + 0.48, color="#F5F6F7", zorder=0)
        start = float(subject["observation_start"])
        end = float(subject["observation_end"])
        ax.hlines(y, start, end, color="#6B7280", linewidth=1.2, zorder=1)
        ax.vlines([start, end], y - 0.10, y + 0.10, color="#6B7280", linewidth=1.0, zorder=1)

    for interval in intervals:
        y = y_by_subject[str(interval["subject_id"])]
        start = float(interval["start"])
        end = float(interval["end"])
        style = interval_styles[str(interval["interval_type"])]
        ax.add_patch(
            Rectangle(
                (start, y - 0.28),
                end - start,
                0.56,
                facecolor=style["color"],
                edgecolor="white",
                linewidth=0.55,
                zorder=2,
            )
        )

    for event in events:
        y = y_by_subject[str(event["subject_id"])]
        style = event_styles[str(event["event_type"])]
        marker = MARKERS[style["marker"]]
        if marker == "x":
            ax.scatter(
                [float(event["time"])], [y], marker=marker, s=52, color=style["color"],
                linewidths=1.6, zorder=4,
            )
        else:
            ax.scatter(
                [float(event["time"])], [y], marker=marker, s=52,
                facecolor=style["color"], edgecolor="white", linewidths=0.8, zorder=4,
            )

    handles: List[object] = [
        Patch(facecolor=style["color"], edgecolor="white", label=style["interval_type_label"])
        for style in interval_styles.values()
    ]
    for style in event_styles.values():
        marker = MARKERS[style["marker"]]
        handles.append(
            Line2D(
                [0], [0], linestyle="None", marker=marker, markersize=6.5,
                markerfacecolor="none" if marker == "x" else style["color"],
                markeredgecolor=style["color"] if marker == "x" else "white",
                markeredgewidth=1.4 if marker == "x" else 0.8,
                color=style["color"], label=style["event_type_label"],
            )
        )
    fig.suptitle(title, y=0.985, fontweight="semibold")
    if handles:
        fig.legend(
            handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.955),
            ncol=legend_columns, frameon=False, handlelength=1.5, columnspacing=1.5,
        )
    ax.set_xlim(xmin - pad, xmax + pad)
    ax.set_ylim(-0.6, n_subjects - 0.4)
    ax.invert_yaxis()
    ax.set_yticks(range(n_subjects))
    ax.set_yticklabels(subject_labels)
    ax.set_xlabel("Time ({})".format(unit))
    ax.xaxis.set_major_locator(MaxNLocator(nbins=9, min_n_ticks=4))
    ax.grid(axis="x", color="#D1D5DB", linewidth=0.7, alpha=0.8, zorder=0)
    ax.tick_params(axis="y", length=0, pad=7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color("#4B5563")
    fig.text(
        0.5, 0.018, "Chronological display only; temporal order does not establish causality.",
        ha="center", va="bottom", fontsize=8, color="#4B5563",
    )
    left = min(0.34, max(0.14, 0.09 + 0.008 * max_subject_chars))
    top = max(0.78, 0.90 - 0.018 * max(0, legend_rows - 1))
    fig.subplots_adjust(left=left, right=0.985, bottom=0.10, top=top)

    png_path = Path(str(output_prefix) + ".png")
    svg_path = Path(str(output_prefix) + ".svg")
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=dpi, facecolor="white", metadata={"Software": "rf-0026 plot.py"})
    fig.savefig(svg_path, facecolor="white", metadata={"Creator": "rf-0026 plot.py"})
    plt.close(fig)
    return png_path, svg_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if (args.events is None) != (args.event_styles is None):
        raise ValidationError("--events and --event-styles must be supplied together or both omitted")
    if args.dpi < 300 or args.dpi > 1200:
        raise ValidationError("--dpi must be an integer from 300 to 1200")
    if args.output_prefix.suffix.lower() in {".png", ".svg", ".pdf"}:
        raise ValidationError("--output-prefix must not include .png, .svg, or .pdf")

    subject_rows, subject_headers = read_csv_table(
        args.subjects,
        "subjects",
        ["subject_id", "subject_label", "display_order", "observation_start", "observation_end", "time_unit"],
    )
    interval_rows, interval_headers = read_csv_table(
        args.intervals,
        "intervals",
        ["interval_id", "subject_id", "start", "end", "interval_type", "time_unit"],
    )
    interval_style_rows, _ = read_csv_table(
        args.interval_styles,
        "interval styles",
        ["interval_type", "interval_type_label", "color"],
    )
    event_rows: List[Dict[str, str]] = []
    event_headers: List[str] = []
    event_style_rows: List[Dict[str, str]] = []
    if args.events is not None and args.event_styles is not None:
        event_rows, event_headers = read_csv_table(
            args.events,
            "events",
            ["event_id", "subject_id", "time", "event_type", "time_unit"],
            allow_empty=True,
        )
        event_style_rows, _ = read_csv_table(
            args.event_styles,
            "event styles",
            ["event_type", "event_type_label", "marker", "color"],
        )

    metadata_tables = [
        ("subjects", subject_rows, subject_headers),
        ("intervals", interval_rows, interval_headers),
    ]
    if args.events is not None:
        metadata_tables.append(("events", event_rows, event_headers))
    validate_metadata(metadata_tables)

    interval_styles = validate_type_styles(
        interval_style_rows, "interval_type", "interval_type_label", "interval styles"
    )
    event_styles: Dict[str, Dict[str, str]] = {}
    if event_style_rows:
        event_styles = validate_type_styles(
            event_style_rows, "event_type", "event_type_label", "event styles"
        )
        marker_problems = [
            "event styles line {} marker {!r} is unsupported; choose {}".format(
                row["__line__"], row["marker"], ", ".join(MARKERS)
            )
            for row in event_style_rows
            if row["marker"] not in MARKERS
        ]
        fail(marker_problems)

    subjects, unit = validate_subjects(subject_rows)
    if len(subjects) > PAGE_LIMIT:
        raise ValidationError(
            "Single-page limit is {} subjects; received {}. Split upstream into contiguous "
            "display_order batches or declared scientific groups, then run each complete batch "
            "separately. Automatic pagination and truncation are disabled.".format(
                PAGE_LIMIT, len(subjects)
            )
        )
    intervals = validate_intervals(interval_rows, subjects, interval_styles, unit)
    events = validate_events(event_rows, subjects, event_styles, unit) if args.events is not None else []
    png_path, svg_path = render(
        subjects, intervals, events, interval_styles, event_styles, unit,
        args.output_prefix, args.title, args.dpi,
    )
    print("Validated {} subjects, {} intervals, and {} events; excluded rows: 0.".format(
        len(subjects), len(intervals), len(events)
    ))
    print("Time unit: {!r}; single-page boundary: {} subjects (no automatic pagination).".format(unit, PAGE_LIMIT))
    print("Wrote {}".format(png_path))
    print("Wrote {}".format(svg_path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValidationError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        sys.exit(2)
