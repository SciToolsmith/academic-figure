#!/usr/bin/env python3
"""Plot supplied survival step coordinates with a supplied risk table."""

from __future__ import annotations

import argparse
import bisect
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt


SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SCRIPT_DIR.parent
DEMO_STEPS = TEMPLATE_DIR / "demo" / "demo_survival_steps_seed18.csv"
DEMO_RISK = TEMPLATE_DIR / "demo" / "demo_risk_table_seed18.csv"
DEMO_ANNOTATIONS = TEMPLATE_DIR / "demo" / "demo_annotations_seed18.csv"
DEFAULT_OUTPUT_PREFIX = Path.cwd() / "survival_supplied_python"
COLORS = ("#287D9B", "#D96B35", "#4F8A5B", "#8D65A8", "#B68A1F", "#5875B5")
BACKGROUND = "#FBFAF7"
INK = "#20282C"
MUTED = "#647078"
GRID = "#E5E2DC"


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class StepRow:
    line: int
    time: float
    estimate: float
    curve_id: str
    status: str
    seed: str


@dataclass(frozen=True)
class RiskRow:
    line: int
    time: float
    curve_id: str
    n_at_risk: int
    status: str
    seed: str


@dataclass(frozen=True)
class AnnotationRow:
    line: int
    time: float
    curve_id: str
    label: str
    status: str
    seed: str


def ordered_unique(values: Iterable[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output


def finite_number(text: str, field: str, line: int) -> float:
    value = text.strip()
    if not value:
        raise ContractError(f"Line {line}: '{field}' must not be blank.")
    try:
        number = float(value)
    except ValueError as exc:
        raise ContractError(f"Line {line}: '{field}' must be numeric.") from exc
    if not math.isfinite(number):
        raise ContractError(f"Line {line}: '{field}' must be finite.")
    return number


def csv_rows(path: Path, required: Sequence[str], label: str) -> List[Tuple[int, Dict[str, str]]]:
    if not path.is_file():
        raise ContractError(f"{label} does not exist: {path}")
    output: List[Tuple[int, Dict[str, str]]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ContractError(f"{label} has no header row.")
        headers = [header.strip() for header in reader.fieldnames]
        if len(headers) != len(set(headers)):
            raise ContractError(f"{label} headers must be unique.")
        missing = set(required) - set(headers)
        if missing:
            raise ContractError(f"{label} is missing columns: {', '.join(sorted(missing))}")
        for line, raw in enumerate(reader, start=2):
            row = {key: str(value or "").strip() for key, value in raw.items()}
            if all(not value for value in row.values()):
                continue
            output.append((line, row))
    if not output:
        raise ContractError(f"{label} contains no data rows.")
    return output


def read_steps(path: Path) -> Tuple[List[StepRow], List[str]]:
    rows: List[StepRow] = []
    for line, row in csv_rows(path, ("time", "estimate", "curve_id"), "Step CSV"):
        curve_id = row["curve_id"]
        if not curve_id:
            raise ContractError(f"Line {line}: curve_id must not be blank.")
        time = finite_number(row["time"], "time", line)
        estimate = finite_number(row["estimate"], "estimate", line)
        if time < 0:
            raise ContractError(f"Line {line}: time must be >= 0.")
        if not 0 <= estimate <= 1:
            raise ContractError(f"Line {line}: estimate must lie in [0, 1].")
        rows.append(StepRow(line, time, estimate, curve_id, row.get("data_status", "").upper(), row.get("simulation_seed", "")))
    curves = ordered_unique(row.curve_id for row in rows)
    for curve in curves:
        subset = [row for row in rows if row.curve_id == curve]
        if len(subset) < 2:
            raise ContractError(f"Curve {curve!r} needs at least two supplied step coordinates.")
        for previous, current in zip(subset, subset[1:]):
            if current.time <= previous.time:
                raise ContractError(
                    f"Curve {curve!r} must appear in strictly increasing time order; "
                    f"line {current.line} follows time {previous.time:g}."
                )
            if current.estimate > previous.estimate + 1e-12:
                raise ContractError(
                    f"Curve {curve!r} increases from {previous.estimate:g} to "
                    f"{current.estimate:g}; supplied survival steps must be non-increasing."
                )
    return rows, curves


def read_risk(path: Path, steps: Sequence[StepRow], curves: Sequence[str]) -> Tuple[List[RiskRow], List[float]]:
    rows: List[RiskRow] = []
    seen = set()
    known = set(curves)
    limits = {
        curve: (
            min(row.time for row in steps if row.curve_id == curve),
            max(row.time for row in steps if row.curve_id == curve),
        )
        for curve in curves
    }
    for line, row in csv_rows(path, ("time", "curve_id", "n_at_risk"), "Risk CSV"):
        curve = row["curve_id"]
        if curve not in known:
            raise ContractError(f"Risk line {line}: unknown curve_id {curve!r}.")
        time = finite_number(row["time"], "time", line)
        if time < 0 or not limits[curve][0] <= time <= limits[curve][1]:
            raise ContractError(
                f"Risk line {line}: time must lie inside the supplied range for {curve!r}."
            )
        text = row["n_at_risk"]
        try:
            count = int(text)
        except ValueError as exc:
            raise ContractError(f"Risk line {line}: n_at_risk must be a nonnegative integer.") from exc
        if count < 0 or str(count) != text:
            raise ContractError(f"Risk line {line}: n_at_risk must be a nonnegative integer.")
        key = (curve, time)
        if key in seen:
            raise ContractError(f"Risk line {line}: duplicate curve_id/time pair.")
        seen.add(key)
        rows.append(RiskRow(line, time, curve, count, row.get("data_status", "").upper(), row.get("simulation_seed", "")))

    grids: List[List[float]] = []
    for curve in curves:
        subset = [row for row in rows if row.curve_id == curve]
        if not subset:
            raise ContractError(f"Risk table is missing curve {curve!r}.")
        times = [row.time for row in subset]
        if any(current <= previous for previous, current in zip(times, times[1:])):
            raise ContractError(f"Risk rows for {curve!r} must appear in strictly increasing time order.")
        grids.append(times)
    if any(grid != grids[0] for grid in grids[1:]):
        raise ContractError("All curves must use the same ordered risk-table time grid.")
    return rows, grids[0]


def read_annotations(
    path: Optional[Path], steps: Sequence[StepRow], curves: Sequence[str]
) -> List[AnnotationRow]:
    if path is None:
        return []
    output: List[AnnotationRow] = []
    seen = set()
    known = set(curves)
    limits = {
        curve: (
            min(row.time for row in steps if row.curve_id == curve),
            max(row.time for row in steps if row.curve_id == curve),
        )
        for curve in curves
    }
    for line, row in csv_rows(path, ("time", "curve_id", "label"), "Annotation CSV"):
        curve = row["curve_id"]
        label = row["label"]
        if curve not in known:
            raise ContractError(f"Annotation line {line}: unknown curve_id {curve!r}.")
        if not label:
            raise ContractError(f"Annotation line {line}: label must not be blank.")
        time = finite_number(row["time"], "time", line)
        if not limits[curve][0] <= time <= limits[curve][1]:
            raise ContractError(f"Annotation line {line}: time is outside the curve range.")
        key = (curve, time)
        if key in seen:
            raise ContractError(f"Annotation line {line}: duplicate curve_id/time pair.")
        seen.add(key)
        output.append(AnnotationRow(line, time, curve, label, row.get("data_status", "").upper(), row.get("simulation_seed", "")))
    return output


def metadata_note(groups: Sequence[Sequence[object]]) -> str:
    rows = [row for group in groups for row in group]
    statuses = ordered_unique(getattr(row, "status") for row in rows if getattr(row, "status"))
    seeds = ordered_unique(getattr(row, "seed") for row in rows if getattr(row, "seed"))
    if len(statuses) > 1 or len(seeds) > 1:
        raise ContractError("data_status and simulation_seed must be constant across all supplied files.")
    if statuses == ["SIMULATED"]:
        if any(getattr(row, "status") != "SIMULATED" or not getattr(row, "seed") for row in rows):
            raise ContractError("Every simulated row in every supplied file must declare the same fixed seed.")
        try:
            seed = int(seeds[0])
        except (IndexError, ValueError) as exc:
            raise ContractError("simulation_seed must be a positive integer.") from exc
        if seed <= 0 or str(seed) != seeds[0]:
            raise ContractError("simulation_seed must be a positive integer.")
        return f"SIMULATED DEMONSTRATION DATA · fixed seed {seed}"
    if seeds:
        raise ContractError("simulation_seed is only valid with SIMULATED data.")
    return "SOURCE-SUPPLIED / PRECOMPUTED DATA"


def step_value(steps: Sequence[StepRow], curve: str, time: float) -> float:
    subset = [row for row in steps if row.curve_id == curve]
    times = [row.time for row in subset]
    index = bisect.bisect_right(times, time) - 1
    return subset[max(index, 0)].estimate


def render(
    steps: Sequence[StepRow],
    risk: Sequence[RiskRow],
    annotations: Sequence[AnnotationRow],
    curves: Sequence[str],
    risk_times: Sequence[float],
    note: str,
    output_prefix: Path,
    title: str,
    x_label: str,
    dpi: int,
) -> Tuple[Path, Path]:
    longest_curve = max(len(curve) for curve in curves)
    width = min(17.0, max(9.0, 7.2 + 0.62 * len(risk_times) + 0.03 * longest_curve))
    height = max(6.4, 4.8 + 0.34 * len(curves))
    figure = plt.figure(figsize=(width, height), facecolor=BACKGROUND)
    grid = figure.add_gridspec(
        2, 1, height_ratios=(3.4, max(1.15, 0.38 * len(curves))),
        left=0.15, right=0.97, top=0.82, bottom=0.14, hspace=0.18
    )
    curve_axis = figure.add_subplot(grid[0, 0])
    risk_axis = figure.add_subplot(grid[1, 0], sharex=curve_axis)
    colors = {curve: COLORS[index % len(COLORS)] for index, curve in enumerate(curves)}

    for curve in curves:
        subset = [row for row in steps if row.curve_id == curve]
        curve_axis.step(
            [row.time for row in subset],
            [row.estimate for row in subset],
            where="post",
            color=colors[curve],
            linewidth=1.8,
            label=curve,
        )
        curve_axis.scatter(
            [row.time for row in subset],
            [row.estimate for row in subset],
            s=18, color=colors[curve], edgecolor="white", linewidth=0.45, zorder=3
        )
    for annotation in annotations:
        y = step_value(steps, annotation.curve_id, annotation.time)
        curve_axis.annotate(
            annotation.label,
            xy=(annotation.time, y),
            xytext=(5, 9),
            textcoords="offset points",
            fontsize=7.4,
            color=colors[annotation.curve_id],
            arrowprops={"arrowstyle": "-", "color": colors[annotation.curve_id], "linewidth": 0.7},
        )
    all_times = [row.time for row in steps]
    span = max(all_times) - min(all_times)
    padding = max(0.02 * span, 0.1)
    curve_axis.set_xlim(min(all_times) - padding, max(all_times) + padding)
    curve_axis.set_ylim(-0.015, 1.025)
    curve_axis.set_ylabel("Supplied survival estimate")
    curve_axis.grid(color=GRID, linewidth=0.65)
    curve_axis.set_axisbelow(True)
    curve_axis.tick_params(axis="x", labelbottom=False)
    curve_axis.legend(frameon=False, ncol=min(4, len(curves)), loc="upper right", fontsize=8.0)
    for spine in ("top", "right"):
        curve_axis.spines[spine].set_visible(False)

    risk_axis.set_ylim(len(curves) - 0.5, -0.5)
    risk_axis.set_yticks(range(len(curves)))
    risk_axis.set_yticklabels(curves, fontsize=8.2)
    risk_axis.set_xticks(risk_times)
    risk_axis.set_xlabel(x_label)
    risk_axis.set_title("Supplied number at risk", loc="left", fontsize=9.2, fontweight="bold", pad=8)
    for row_index in range(len(curves)):
        if row_index % 2 == 0:
            risk_axis.axhspan(row_index - 0.5, row_index + 0.5, color="#F1EFE9", zorder=0)
    risk_lookup = {(row.curve_id, row.time): row.n_at_risk for row in risk}
    for row_index, curve in enumerate(curves):
        for time in risk_times:
            risk_axis.text(time, row_index, str(risk_lookup[(curve, time)]), ha="center", va="center", fontsize=8.0, color=INK)
    risk_axis.grid(axis="x", color=GRID, linewidth=0.55)
    risk_axis.tick_params(axis="y", length=0, pad=8)
    for spine in ("top", "right", "left"):
        risk_axis.spines[spine].set_visible(False)

    figure.text(0.04, 0.975, title, ha="left", va="top", fontsize=18, fontweight="bold", color=INK)
    figure.text(0.04, 0.928, note, ha="left", va="top", fontsize=9.0, color=MUTED)
    figure.text(
        0.04, 0.890,
        "SUPPLIED/PRECOMPUTED coordinates, risk counts, and optional annotations; no Kaplan–Meier fit, confidence interval, or log-rank test is computed.",
        ha="left", va="top", fontsize=8.2, color=MUTED,
    )
    figure.text(
        0.04, 0.025,
        "Step convention: each estimate is held from its supplied time until the next supplied coordinate (post step). Statistical interpretation remains upstream.",
        ha="left", va="bottom", fontsize=7.6, color=MUTED,
    )
    prefix = output_prefix.expanduser().with_suffix("")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    png_path = prefix.with_suffix(".png")
    svg_path = prefix.with_suffix(".svg")
    figure.savefig(png_path, dpi=dpi, bbox_inches="tight", facecolor=BACKGROUND)
    figure.savefig(svg_path, bbox_inches="tight", facecolor=BACKGROUND)
    plt.close(figure)
    return png_path, svg_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot supplied survival steps and risk counts without fitting a model.")
    parser.add_argument("--steps", type=Path)
    parser.add_argument("--risk", type=Path)
    parser.add_argument("--annotations", type=Path)
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT_PREFIX)
    parser.add_argument("--title", default="Supplied survival step coordinates")
    parser.add_argument("--x-label", default="Time")
    parser.add_argument("--dpi", type=int, default=320)
    args = parser.parse_args()
    if (args.steps is None) != (args.risk is None):
        parser.error("Provide --steps and --risk together.")
    if args.steps is None:
        args.steps = DEMO_STEPS
        args.risk = DEMO_RISK
        if args.annotations is None:
            args.annotations = DEMO_ANNOTATIONS
    if args.dpi < 150:
        parser.error("--dpi must be at least 150.")
    return args


def main() -> int:
    args = parse_args()
    try:
        steps, curves = read_steps(args.steps.expanduser())
        risk, risk_times = read_risk(args.risk.expanduser(), steps, curves)
        annotations = read_annotations(
            args.annotations.expanduser() if args.annotations else None, steps, curves
        )
        note = metadata_note((steps, risk, annotations))
        png_path, svg_path = render(
            steps, risk, annotations, curves, risk_times, note,
            args.output_prefix, args.title, args.x_label, args.dpi
        )
    except ContractError as exc:
        raise SystemExit(f"Input validation failed: {exc}") from exc
    print(
        f"Validated {len(steps)} supplied step coordinates, {len(risk)} risk counts, "
        f"{len(annotations)} supplied annotations, {len(curves)} curves"
    )
    print(f"Data status: {note}")
    print(f"PNG: {png_path.resolve()}")
    print(f"SVG: {svg_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
