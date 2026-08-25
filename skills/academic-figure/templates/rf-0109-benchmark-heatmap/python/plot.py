#!/usr/bin/env python3
"""Render a direction-aware benchmark heatmap from validated long-form CSV files."""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap


SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SCRIPT_DIR.parent
DEFAULT_INPUT = TEMPLATE_DIR / "demo" / "demo_benchmark_seed109.csv"
DEFAULT_SPEC = TEMPLATE_DIR / "demo" / "demo_metric_spec.csv"
DEFAULT_OUTPUT_PREFIX = Path.cwd() / "benchmark_heatmap_python"

MAX_METRICS = 18
MAX_METHODS = 80
BACKGROUND = "#FBFAF7"
INK = "#20282C"
MUTED = "#637078"
MISSING = "#DDDCD7"


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class MetricSpec:
    metric: str
    label: str
    direction: str
    display: str
    digits: int
    scale_min: float
    scale_max: float


def ordered_unique(values: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def parse_finite(text: str, field: str, line: int, allow_blank: bool = False) -> Optional[float]:
    value = text.strip()
    if not value:
        if allow_blank:
            return None
        raise ContractError(f"Line {line}: '{field}' must not be blank.")
    try:
        number = float(value)
    except ValueError as exc:
        raise ContractError(f"Line {line}: '{field}' must be numeric, got {value!r}.") from exc
    if not math.isfinite(number):
        raise ContractError(f"Line {line}: '{field}' must be finite.")
    return number


def read_metric_spec(path: Path) -> Tuple[List[MetricSpec], Dict[str, MetricSpec]]:
    if not path.is_file():
        raise ContractError(f"Metric spec does not exist: {path}")
    required = {"metric", "label", "direction", "display", "digits", "scale_min", "scale_max"}
    specs: List[MetricSpec] = []
    seen = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ContractError("Metric spec has no header row.")
        headers = [header.strip() for header in reader.fieldnames]
        if len(headers) != len(set(headers)):
            raise ContractError("Metric spec headers must be unique.")
        missing = sorted(required - set(headers))
        if missing:
            raise ContractError(f"Metric spec is missing columns: {', '.join(missing)}")
        for line, row in enumerate(reader, start=2):
            if all(not str(value or "").strip() for value in row.values()):
                continue
            metric = str(row.get("metric", "") or "").strip()
            label = str(row.get("label", "") or "").strip()
            direction = str(row.get("direction", "") or "").strip().lower()
            display = str(row.get("display", "") or "").strip().lower()
            if not metric or not label:
                raise ContractError(f"Metric spec line {line}: metric and label are required.")
            if metric in seen:
                raise ContractError(f"Metric spec line {line}: duplicate metric {metric!r}.")
            if direction not in {"higher", "lower"}:
                raise ContractError(
                    f"Metric spec line {line}: direction must be 'higher' or 'lower'."
                )
            if display not in {"decimal", "percent", "integer", "scientific"}:
                raise ContractError(
                    f"Metric spec line {line}: unsupported display {display!r}."
                )
            digits_text = str(row.get("digits", "") or "").strip()
            try:
                digits = int(digits_text)
            except ValueError as exc:
                raise ContractError(
                    f"Metric spec line {line}: digits must be an integer from 0 to 6."
                ) from exc
            if not 0 <= digits <= 6 or str(digits) != digits_text:
                raise ContractError(
                    f"Metric spec line {line}: digits must be an integer from 0 to 6."
                )
            scale_min = parse_finite(str(row.get("scale_min", "") or ""), "scale_min", line)
            scale_max = parse_finite(str(row.get("scale_max", "") or ""), "scale_max", line)
            assert scale_min is not None and scale_max is not None
            if not scale_min < scale_max:
                raise ContractError(
                    f"Metric spec line {line}: require scale_min < scale_max."
                )
            seen.add(metric)
            specs.append(
                MetricSpec(metric, label, direction, display, digits, scale_min, scale_max)
            )
    if not specs:
        raise ContractError("Metric spec contains no metrics.")
    if len(specs) > MAX_METRICS:
        raise ContractError(
            f"Metric spec contains {len(specs)} metrics; the readable limit is {MAX_METRICS}. "
            "Split the benchmark into coherent metric panels."
        )
    return specs, {spec.metric: spec for spec in specs}


def read_scores(
    path: Path, specs: Sequence[MetricSpec], spec_by_id: Dict[str, MetricSpec]
) -> Tuple[List[str], Dict[Tuple[str, str], Optional[float]], str, int]:
    if not path.is_file():
        raise ContractError(f"Benchmark CSV does not exist: {path}")
    required = {"method", "metric", "value"}
    methods: List[str] = []
    values: Dict[Tuple[str, str], Optional[float]] = {}
    statuses: List[str] = []
    seeds: List[str] = []
    row_count = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ContractError("Benchmark CSV has no header row.")
        headers = [header.strip() for header in reader.fieldnames]
        if len(headers) != len(set(headers)):
            raise ContractError("Benchmark CSV headers must be unique.")
        missing = sorted(required - set(headers))
        if missing:
            raise ContractError(f"Benchmark CSV is missing columns: {', '.join(missing)}")
        for line, row in enumerate(reader, start=2):
            if all(not str(value or "").strip() for value in row.values()):
                continue
            row_count += 1
            method = str(row.get("method", "") or "").strip()
            metric = str(row.get("metric", "") or "").strip()
            if not method or not metric:
                raise ContractError(f"Line {line}: method and metric are required.")
            if metric not in spec_by_id:
                raise ContractError(f"Line {line}: unknown metric {metric!r}.")
            key = (method, metric)
            if key in values:
                raise ContractError(
                    f"Line {line}: duplicate method/metric pair {method!r} + {metric!r}."
                )
            if method not in methods:
                methods.append(method)
            number = parse_finite(
                str(row.get("value", "") or ""), "value", line, allow_blank=True
            )
            spec = spec_by_id[metric]
            if number is not None:
                if not spec.scale_min <= number <= spec.scale_max:
                    raise ContractError(
                        f"Line {line}: value {number:g} lies outside the declared scale "
                        f"[{spec.scale_min:g}, {spec.scale_max:g}] for {metric!r}."
                    )
                if spec.display == "integer" and not math.isclose(
                    number, round(number), abs_tol=1e-9
                ):
                    raise ContractError(
                        f"Line {line}: integer display requires an integer-valued input."
                    )
            values[key] = number
            status = str(row.get("data_status", "") or "").strip().upper()
            seed = str(row.get("simulation_seed", "") or "").strip()
            if status:
                statuses.append(status)
            if seed:
                seeds.append(seed)

    if not methods:
        raise ContractError("Benchmark CSV contains no data rows.")
    if len(methods) > MAX_METHODS:
        raise ContractError(
            f"Benchmark contains {len(methods)} methods; the readable limit is {MAX_METHODS}. "
            "Filter or split the benchmark before plotting."
        )
    expected = {(method, spec.metric) for method in methods for spec in specs}
    missing_pairs = expected - set(values)
    if missing_pairs:
        method, metric = sorted(missing_pairs)[0]
        raise ContractError(
            f"The long table must contain every method/metric pair; missing {method!r} + {metric!r}. "
            "Use a blank value to represent an explicit NA."
        )

    unique_statuses = ordered_unique(statuses)
    unique_seeds = ordered_unique(seeds)
    if len(unique_statuses) > 1:
        raise ContractError("data_status must be constant across the benchmark CSV.")
    if len(unique_seeds) > 1:
        raise ContractError("simulation_seed must be constant across the benchmark CSV.")
    if unique_statuses == ["SIMULATED"]:
        if len(statuses) != row_count or len(seeds) != row_count:
            raise ContractError(
                "Every simulated row must declare data_status=SIMULATED and one fixed seed."
            )
        try:
            seed_number = int(unique_seeds[0])
        except (IndexError, ValueError) as exc:
            raise ContractError("simulation_seed must be a positive integer.") from exc
        if seed_number <= 0 or str(seed_number) != unique_seeds[0]:
            raise ContractError("simulation_seed must be a positive integer.")
        data_note = f"SIMULATED DEMONSTRATION DATA · fixed seed {seed_number}"
    else:
        if unique_seeds:
            raise ContractError(
                "simulation_seed is only valid when data_status is SIMULATED."
            )
        data_note = "SOURCE-SUPPLIED DATA"
    return methods, values, data_note, row_count


def performance(value: float, spec: MetricSpec) -> float:
    scaled = (value - spec.scale_min) / (spec.scale_max - spec.scale_min)
    return scaled if spec.direction == "higher" else 1.0 - scaled


def format_value(value: Optional[float], spec: MetricSpec) -> str:
    if value is None:
        return "NA"
    if spec.display == "percent":
        return f"{100.0 * value:.{spec.digits}f}%"
    if spec.display == "integer":
        return f"{value:.0f}"
    if spec.display == "scientific":
        return f"{value:.{spec.digits}e}"
    return f"{value:.{spec.digits}f}"


def rank_methods(
    methods: Sequence[str],
    specs: Sequence[MetricSpec],
    values: Dict[Tuple[str, str], Optional[float]],
) -> Tuple[List[str], Dict[str, Optional[float]], Dict[str, Optional[int]]]:
    scores: Dict[str, Optional[float]] = {}
    coverage: Dict[str, int] = {}
    available_scores: Dict[str, float] = {}
    for method in methods:
        per_metric = [
            performance(value, spec)
            for spec in specs
            if (value := values[(method, spec.metric)]) is not None
        ]
        coverage[method] = len(per_metric)
        available_scores[method] = sum(per_metric) / len(per_metric) if per_metric else -math.inf
        scores[method] = (
            available_scores[method] if len(per_metric) == len(specs) else None
        )

    complete = [method for method in methods if scores[method] is not None]
    complete.sort(key=lambda method: (-float(scores[method]), method.casefold()))
    ranks: Dict[str, Optional[int]] = {method: None for method in methods}
    previous_score: Optional[float] = None
    previous_rank = 0
    for position, method in enumerate(complete, start=1):
        score = float(scores[method])
        if previous_score is not None and math.isclose(
            score, previous_score, rel_tol=0.0, abs_tol=1e-12
        ):
            ranks[method] = previous_rank
        else:
            ranks[method] = position
            previous_rank = position
            previous_score = score

    incomplete = [method for method in methods if scores[method] is None]
    incomplete.sort(
        key=lambda method: (
            -coverage[method],
            -available_scores[method],
            method.casefold(),
        )
    )
    return complete + incomplete, scores, ranks


def render(
    methods: Sequence[str],
    specs: Sequence[MetricSpec],
    values: Dict[Tuple[str, str], Optional[float]],
    data_note: str,
    output_prefix: Path,
    title: str,
    dpi: int,
) -> Tuple[Path, Path, int]:
    ordered_methods, overall_scores, ranks = rank_methods(methods, specs, values)
    matrix = np.full((len(ordered_methods), len(specs)), np.nan, dtype=float)
    labels: List[List[str]] = []
    for row_index, method in enumerate(ordered_methods):
        row_labels: List[str] = []
        for col_index, spec in enumerate(specs):
            value = values[(method, spec.metric)]
            row_labels.append(format_value(value, spec))
            if value is not None:
                matrix[row_index, col_index] = performance(value, spec)
        labels.append(row_labels)

    longest_method = max(len(method) for method in ordered_methods)
    width = min(22.0, max(8.8, 3.3 + 1.55 * len(specs) + 0.035 * longest_method))
    height = max(5.2, 2.4 + 0.52 * len(ordered_methods))
    figure, axis = plt.subplots(figsize=(width, height), facecolor=BACKGROUND)
    figure.subplots_adjust(left=min(0.30, 0.14 + 0.004 * longest_method), right=0.985, top=0.79, bottom=0.20)

    cmap = LinearSegmentedColormap.from_list(
        "benchmark_performance", ["#B75C45", "#F0EADF", "#277C80"]
    ).with_extremes(bad=MISSING)
    image = axis.imshow(matrix, vmin=0.0, vmax=1.0, cmap=cmap, aspect="auto")
    axis.set_facecolor(BACKGROUND)
    axis.set_xticks(range(len(specs)))
    axis.set_xticklabels(
        [
            f"{spec.label}\n{'higher is better' if spec.direction == 'higher' else 'lower is better'}"
            for spec in specs
        ],
        rotation=32 if len(specs) > 10 else 0,
        ha="right" if len(specs) > 10 else "center",
        fontsize=max(6.4, 8.4 - 0.10 * max(0, len(specs) - 8)),
    )
    axis.xaxis.tick_top()
    axis.tick_params(axis="x", length=0, pad=8)
    axis.set_yticks(range(len(ordered_methods)))
    axis.set_yticklabels(
        [
            f"#{ranks[method]}  {method}" if ranks[method] is not None else f"NR  {method}"
            for method in ordered_methods
        ],
        fontsize=max(6.8, 8.8 - 0.04 * max(0, len(ordered_methods) - 20)),
    )
    axis.tick_params(axis="y", length=0, pad=7)
    axis.set_xticks(np.arange(-0.5, len(specs), 1), minor=True)
    axis.set_yticks(np.arange(-0.5, len(ordered_methods), 1), minor=True)
    axis.grid(which="minor", color=BACKGROUND, linewidth=2.0)
    axis.tick_params(which="minor", bottom=False, left=False)
    for spine in axis.spines.values():
        spine.set_visible(False)

    text_size = max(5.5, 8.2 - 0.16 * max(0, len(specs) - 8))
    for row_index in range(len(ordered_methods)):
        for col_index in range(len(specs)):
            score = matrix[row_index, col_index]
            text_color = "#FFFFFF" if math.isfinite(score) and (score < 0.19 or score > 0.81) else INK
            axis.text(
                col_index,
                row_index,
                labels[row_index][col_index],
                ha="center",
                va="center",
                fontsize=text_size,
                color=text_color,
                fontweight="semibold" if math.isfinite(score) else "normal",
            )

    figure.text(0.035, 0.975, title, ha="left", va="top", fontsize=18, fontweight="bold", color=INK)
    figure.text(0.035, 0.925, data_note, ha="left", va="top", fontsize=9.0, color=MUTED)
    figure.text(
        0.035,
        0.890,
        "Cell text = original value · color = direction-aligned performance on the metric's declared [scale_min, scale_max]",
        ha="left",
        va="top",
        fontsize=8.2,
        color=MUTED,
    )
    colorbar = figure.colorbar(image, ax=axis, orientation="horizontal", fraction=0.045, pad=0.13, aspect=40)
    colorbar.set_ticks([0.0, 0.5, 1.0])
    colorbar.set_ticklabels(["0 · worse", "0.5", "1 · better"])
    colorbar.set_label("Comparable normalized performance", fontsize=8.2)
    colorbar.ax.tick_params(labelsize=7.6)
    incomplete_count = sum(overall_scores[method] is None for method in methods)
    figure.text(
        0.035,
        0.025,
        f"Complete methods are ordered by equal-weight mean normalized performance; exact ties share competition rank. "
        f"NR = not ranked because at least one metric is NA ({incomplete_count} method(s)). No significance testing is performed.",
        ha="left",
        va="bottom",
        fontsize=7.5,
        color=MUTED,
    )

    prefix = output_prefix.expanduser().with_suffix("")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    png_path = prefix.with_suffix(".png")
    svg_path = prefix.with_suffix(".svg")
    figure.savefig(png_path, dpi=dpi, bbox_inches="tight", facecolor=BACKGROUND)
    figure.savefig(svg_path, bbox_inches="tight", facecolor=BACKGROUND)
    plt.close(figure)
    return png_path, svg_path, incomplete_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a validated benchmark heatmap.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--metric-spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT_PREFIX)
    parser.add_argument("--title", default="Benchmark performance matrix")
    parser.add_argument("--dpi", type=int, default=320)
    args = parser.parse_args()
    if args.dpi < 150:
        parser.error("--dpi must be at least 150.")
    return args


def main() -> int:
    args = parse_args()
    try:
        specs, spec_by_id = read_metric_spec(args.metric_spec.expanduser())
        methods, values, data_note, row_count = read_scores(
            args.input.expanduser(), specs, spec_by_id
        )
        png_path, svg_path, incomplete_count = render(
            methods, specs, values, data_note, args.output_prefix, args.title, args.dpi
        )
    except ContractError as exc:
        raise SystemExit(f"Input validation failed: {exc}") from exc
    missing_count = sum(value is None for value in values.values())
    print(
        f"Validated {row_count} rows: {len(methods)} methods × {len(specs)} metrics; "
        f"{missing_count} explicit NA cells; {incomplete_count} unranked method(s)"
    )
    print(f"Data status: {data_note}")
    print(f"PNG: {png_path.resolve()}")
    print(f"SVG: {svg_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
