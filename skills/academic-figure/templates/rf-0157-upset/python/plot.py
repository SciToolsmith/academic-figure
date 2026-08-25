#!/usr/bin/env python3
"""Render exact item-set intersections as an UpSet plot."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set, Tuple

import matplotlib.pyplot as plt


SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SCRIPT_DIR.parent
DEFAULT_INPUT = TEMPLATE_DIR / "demo" / "demo_membership_seed157.csv"
DEFAULT_SPEC = TEMPLATE_DIR / "demo" / "demo_set_spec.csv"
DEFAULT_OUTPUT_PREFIX = Path.cwd() / "upset_python"
MAX_SETS = 16
MAX_TOP = 50
BACKGROUND = "#FBFAF7"
INK = "#20282C"
MUTED = "#647078"
ACCENT = "#287D87"
INACTIVE = "#D8D9D5"
GRID = "#E5E2DC"


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class SetSpec:
    set_id: str
    label: str


def ordered_unique(values: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def read_set_spec(path: Path) -> List[SetSpec]:
    if not path.is_file():
        raise ContractError(f"Set spec does not exist: {path}")
    specs: List[SetSpec] = []
    seen_ids = set()
    seen_labels = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ContractError("Set spec has no header row.")
        headers = [header.strip() for header in reader.fieldnames]
        if len(headers) != len(set(headers)):
            raise ContractError("Set spec headers must be unique.")
        missing = {"set", "label"} - set(headers)
        if missing:
            raise ContractError(f"Set spec is missing columns: {', '.join(sorted(missing))}")
        for line, row in enumerate(reader, start=2):
            if all(not str(value or "").strip() for value in row.values()):
                continue
            set_id = str(row.get("set", "") or "").strip()
            label = str(row.get("label", "") or "").strip()
            if not set_id or not label:
                raise ContractError(f"Set spec line {line}: set and label must be nonblank.")
            if set_id in seen_ids:
                raise ContractError(f"Set spec line {line}: duplicate set ID {set_id!r}.")
            if label in seen_labels:
                raise ContractError(f"Set spec line {line}: duplicate display label {label!r}.")
            seen_ids.add(set_id)
            seen_labels.add(label)
            specs.append(SetSpec(set_id, label))
    if len(specs) < 2:
        raise ContractError("UpSet requires at least two declared sets.")
    if len(specs) > MAX_SETS:
        raise ContractError(
            f"Set spec declares {len(specs)} sets; the readable limit is {MAX_SETS}. "
            "Split the set family into interpretable subsets."
        )
    return specs


def read_memberships(
    path: Path, specs: Sequence[SetSpec]
) -> Tuple[List[str], Dict[str, Set[str]], str, int]:
    if not path.is_file():
        raise ContractError(f"Membership CSV does not exist: {path}")
    known_sets = {spec.set_id for spec in specs}
    items: List[str] = []
    memberships: Dict[str, Set[str]] = defaultdict(set)
    seen_pairs = set()
    statuses: List[str] = []
    seeds: List[str] = []
    row_count = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ContractError("Membership CSV has no header row.")
        headers = [header.strip() for header in reader.fieldnames]
        if len(headers) != len(set(headers)):
            raise ContractError("Membership CSV headers must be unique.")
        missing = {"item", "set"} - set(headers)
        if missing:
            raise ContractError(
                f"Membership CSV is missing columns: {', '.join(sorted(missing))}"
            )
        for line, row in enumerate(reader, start=2):
            if all(not str(value or "").strip() for value in row.values()):
                continue
            row_count += 1
            item = str(row.get("item", "") or "").strip()
            set_id = str(row.get("set", "") or "").strip()
            if not item or not set_id:
                raise ContractError(
                    f"Line {line}: item and set must be nonblank; empty memberships are invalid."
                )
            if set_id not in known_sets:
                raise ContractError(f"Line {line}: unknown set {set_id!r}.")
            pair = (item, set_id)
            if pair in seen_pairs:
                raise ContractError(
                    f"Line {line}: duplicate membership {item!r} + {set_id!r}."
                )
            seen_pairs.add(pair)
            if item not in memberships:
                items.append(item)
            memberships[item].add(set_id)
            status = str(row.get("data_status", "") or "").strip().upper()
            seed = str(row.get("simulation_seed", "") or "").strip()
            if status:
                statuses.append(status)
            if seed:
                seeds.append(seed)

    if not items:
        raise ContractError("Membership CSV contains no memberships.")
    unused_sets = [spec.set_id for spec in specs if not any(spec.set_id in memberships[item] for item in items)]
    if unused_sets:
        raise ContractError(
            "Declared sets must not be empty; no membership found for: "
            + ", ".join(unused_sets)
        )

    unique_statuses = ordered_unique(statuses)
    unique_seeds = ordered_unique(seeds)
    if len(unique_statuses) > 1 or len(unique_seeds) > 1:
        raise ContractError("data_status and simulation_seed must each be constant.")
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
    return items, dict(memberships), data_note, row_count


def exact_intersections(
    items: Sequence[str], memberships: Dict[str, Set[str]], specs: Sequence[SetSpec]
) -> Counter[Tuple[int, ...]]:
    set_order = [spec.set_id for spec in specs]
    counts: Counter[Tuple[int, ...]] = Counter()
    for item in items:
        combination = tuple(
            index for index, set_id in enumerate(set_order) if set_id in memberships[item]
        )
        if not combination:
            raise ContractError(f"Item {item!r} has no declared-set membership.")
        counts[combination] += 1
    return counts


def sort_intersections(
    counts: Counter[Tuple[int, ...]], top: int
) -> Tuple[List[Tuple[Tuple[int, ...], int]], int]:
    ordered = sorted(
        counts.items(),
        key=lambda entry: (-entry[1], -len(entry[0]), entry[0]),
    )
    shown = ordered[:top]
    return shown, len(ordered) - len(shown)


def render(
    items: Sequence[str],
    memberships: Dict[str, Set[str]],
    specs: Sequence[SetSpec],
    data_note: str,
    output_prefix: Path,
    title: str,
    top: int,
    dpi: int,
) -> Tuple[Path, Path, int, int]:
    counts = exact_intersections(items, memberships, specs)
    displayed, hidden_count = sort_intersections(counts, top)
    set_sizes = [
        sum(spec.set_id in memberships[item] for item in items) for spec in specs
    ]
    intersection_count = len(displayed)
    set_count = len(specs)
    width = min(23.0, max(10.0, 4.3 + 0.58 * intersection_count))
    height = max(6.3, 3.6 + 0.38 * set_count)

    figure = plt.figure(figsize=(width, height), facecolor=BACKGROUND)
    grid = figure.add_gridspec(
        2,
        2,
        width_ratios=(2.0, max(4.5, 0.52 * intersection_count)),
        height_ratios=(2.25, max(2.3, 0.38 * set_count)),
        left=0.08,
        right=0.98,
        bottom=0.12,
        top=0.82,
        wspace=0.12,
        hspace=0.06,
    )
    info_axis = figure.add_subplot(grid[0, 0])
    bar_axis = figure.add_subplot(grid[0, 1])
    size_axis = figure.add_subplot(grid[1, 0])
    matrix_axis = figure.add_subplot(grid[1, 1], sharex=bar_axis, sharey=size_axis)

    for axis in (info_axis, bar_axis, size_axis, matrix_axis):
        axis.set_facecolor(BACKGROUND)
    info_axis.axis("off")
    info_axis.text(0.0, 0.92, "Exact-membership summary", fontsize=10.5, fontweight="bold", color=INK)
    info_axis.text(
        0.0,
        0.73,
        f"{len(items)} unique items\n{set_count} declared sets\n{len(counts)} nonzero exact intersections\n{intersection_count} displayed · {hidden_count} not displayed",
        fontsize=8.8,
        color=MUTED,
        va="top",
        linespacing=1.55,
    )

    x_positions = list(range(intersection_count))
    intersection_sizes = [count for _combination, count in displayed]
    bar_axis.bar(x_positions, intersection_sizes, width=0.72, color=ACCENT, edgecolor="white", linewidth=0.6)
    max_intersection = max(intersection_sizes)
    for x_value, count in zip(x_positions, intersection_sizes):
        bar_axis.text(x_value, count + max_intersection * 0.025, str(count), ha="center", va="bottom", fontsize=max(6.2, 8.0 - 0.06 * max(0, intersection_count - 18)), color=INK)
    bar_axis.set_ylim(0, max_intersection * 1.22)
    bar_axis.set_ylabel("Exact intersection size")
    bar_axis.set_title("Top exact intersections", loc="left", fontsize=11.5, fontweight="bold")
    bar_axis.grid(axis="y", color=GRID, linewidth=0.65)
    bar_axis.set_axisbelow(True)
    bar_axis.tick_params(axis="x", bottom=False, labelbottom=False)
    for spine in ("top", "right"):
        bar_axis.spines[spine].set_visible(False)

    y_positions = list(range(set_count))
    size_axis.barh(y_positions, set_sizes, height=0.58, color="#81979A", edgecolor="white", linewidth=0.5)
    size_axis.set_ylim(set_count - 0.5, -0.5)
    size_axis.set_yticks(y_positions)
    size_axis.set_yticklabels([spec.label for spec in specs], fontsize=max(7.0, 8.8 - 0.06 * max(0, set_count - 10)))
    size_axis.set_xlabel("Set size")
    size_axis.set_title("Set sizes", loc="left", fontsize=10.5, fontweight="bold")
    size_axis.grid(axis="x", color=GRID, linewidth=0.65)
    size_axis.set_axisbelow(True)
    max_set_size = max(set_sizes)
    size_axis.set_xlim(0, max_set_size * 1.24)
    for y_value, count in zip(y_positions, set_sizes):
        size_axis.text(count + max_set_size * 0.025, y_value, str(count), ha="left", va="center", fontsize=7.5, color=INK)
    for spine in ("top", "right"):
        size_axis.spines[spine].set_visible(False)

    matrix_axis.set_xlim(-0.5, intersection_count - 0.5)
    matrix_axis.set_ylim(set_count - 0.5, -0.5)
    for y_value in y_positions:
        if y_value % 2 == 0:
            matrix_axis.axhspan(y_value - 0.5, y_value + 0.5, color="#F2F0EA", zorder=0)
    for x_value, (combination, _count) in zip(x_positions, displayed):
        matrix_axis.scatter(
            [x_value] * set_count,
            y_positions,
            s=28,
            color=INACTIVE,
            edgecolor="none",
            zorder=1,
        )
        active_y = list(combination)
        if len(active_y) > 1:
            matrix_axis.plot(
                [x_value, x_value],
                [min(active_y), max(active_y)],
                color=INK,
                linewidth=1.5,
                zorder=2,
            )
        matrix_axis.scatter(
            [x_value] * len(active_y),
            active_y,
            s=40,
            color=INK,
            edgecolor="white",
            linewidth=0.4,
            zorder=3,
        )
    matrix_axis.set_xticks(x_positions)
    matrix_axis.set_xticklabels([str(index) for index in range(1, intersection_count + 1)], fontsize=max(5.8, 7.6 - 0.06 * max(0, intersection_count - 18)))
    matrix_axis.set_xlabel("Displayed intersection rank")
    matrix_axis.tick_params(axis="y", left=False, labelleft=False)
    for spine in ("top", "right", "left"):
        matrix_axis.spines[spine].set_visible(False)

    figure.text(0.035, 0.975, title, ha="left", va="top", fontsize=18, fontweight="bold", color=INK)
    figure.text(0.035, 0.925, data_note, ha="left", va="top", fontsize=9.0, color=MUTED)
    figure.text(
        0.035,
        0.888,
        "Each item contributes once to exactly one membership combination; bars are not inclusive overlaps.",
        ha="left",
        va="top",
        fontsize=8.2,
        color=MUTED,
    )
    figure.text(
        0.035,
        0.025,
        f"Selection: size descending, then degree descending, then declared-set index tuple ascending. "
        f"Displayed {intersection_count} of {len(counts)} nonzero exact intersections; {hidden_count} not displayed.",
        ha="left",
        va="bottom",
        fontsize=7.7,
        color=MUTED,
    )

    prefix = output_prefix.expanduser().with_suffix("")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    png_path = prefix.with_suffix(".png")
    svg_path = prefix.with_suffix(".svg")
    figure.savefig(png_path, dpi=dpi, bbox_inches="tight", facecolor=BACKGROUND)
    figure.savefig(svg_path, bbox_inches="tight", facecolor=BACKGROUND)
    plt.close(figure)
    return png_path, svg_path, len(counts), hidden_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render exact item-set memberships as an UpSet plot.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--set-spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT_PREFIX)
    parser.add_argument("--title", default="Exact set intersections")
    parser.add_argument("--top", type=int, default=12)
    parser.add_argument("--dpi", type=int, default=320)
    args = parser.parse_args()
    if not 1 <= args.top <= MAX_TOP:
        parser.error(f"--top must be between 1 and {MAX_TOP}.")
    if args.dpi < 150:
        parser.error("--dpi must be at least 150.")
    return args


def main() -> int:
    args = parse_args()
    try:
        specs = read_set_spec(args.set_spec.expanduser())
        items, memberships, data_note, row_count = read_memberships(
            args.input.expanduser(), specs
        )
        png_path, svg_path, intersection_count, hidden_count = render(
            items,
            memberships,
            specs,
            data_note,
            args.output_prefix,
            args.title,
            args.top,
            args.dpi,
        )
    except ContractError as exc:
        raise SystemExit(f"Input validation failed: {exc}") from exc
    print(
        f"Validated {row_count} unique memberships: {len(items)} items × {len(specs)} sets; "
        f"{intersection_count} nonzero exact intersections; "
        f"{intersection_count - hidden_count} displayed; {hidden_count} not displayed"
    )
    print(f"Data status: {data_note}")
    print(f"PNG: {png_path.resolve()}")
    print(f"SVG: {svg_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
