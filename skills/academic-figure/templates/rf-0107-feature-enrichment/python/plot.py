#!/usr/bin/env python3
"""Visualize supplied feature statistics and precomputed enrichment coordinates."""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt


SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SCRIPT_DIR.parent
DEMO_FEATURES = TEMPLATE_DIR / "demo" / "demo_features_seed107.csv"
DEMO_CURVES = TEMPLATE_DIR / "demo" / "demo_ranked_curves_seed107.csv"
DEMO_HITS = TEMPLATE_DIR / "demo" / "demo_hits_seed107.csv"
DEMO_SUMMARY = TEMPLATE_DIR / "demo" / "demo_summary_seed107.csv"
DEFAULT_OUTPUT_PREFIX = Path.cwd() / "feature_enrichment_python"
BACKGROUND = "#FBFAF7"
INK = "#20282C"
MUTED = "#647078"
GRID = "#E5E2DC"
COLORS = ("#287D9B", "#D96B35", "#4F8A5B", "#8D65A8", "#B68A1F", "#5875B5", "#B64E68")
MAX_CURVES = 8


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class FeatureRow:
    line: int
    feature: str
    effect: float
    significance: float
    category: str
    status: str
    seed: str


@dataclass(frozen=True)
class CurveRow:
    line: int
    curve_id: str
    rank: int
    running_score: float
    status: str
    seed: str


@dataclass(frozen=True)
class HitRow:
    line: int
    curve_id: str
    rank: int
    status: str
    seed: str


@dataclass(frozen=True)
class SummaryRow:
    line: int
    curve_id: str
    enrichment_score: float
    p_value: Optional[float]
    adjusted_p_value: Optional[float]
    hit_count: Optional[int]
    status: str
    seed: str


def ordered_unique(values: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def finite_number(text: str, field: str, line: int, allow_blank: bool = False) -> Optional[float]:
    value = text.strip()
    if not value:
        if allow_blank:
            return None
        raise ContractError(f"Line {line}: '{field}' must not be blank.")
    try:
        number = float(value)
    except ValueError as exc:
        raise ContractError(f"Line {line}: '{field}' must be numeric.") from exc
    if not math.isfinite(number):
        raise ContractError(f"Line {line}: '{field}' must be finite.")
    return number


def positive_integer(text: str, field: str, line: int, allow_blank: bool = False) -> Optional[int]:
    value = text.strip()
    if not value and allow_blank:
        return None
    try:
        number = int(value)
    except ValueError as exc:
        raise ContractError(f"Line {line}: '{field}' must be a positive integer.") from exc
    if number <= 0 or str(number) != value:
        raise ContractError(f"Line {line}: '{field}' must be a positive integer.")
    return number


def csv_rows(path: Path, required: Sequence[str], label: str) -> Tuple[List[str], List[Tuple[int, Dict[str, str]]]]:
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
    return headers, output


def read_features(
    path: Optional[Path], effect_threshold: Optional[float], significance_threshold: Optional[float]
) -> Tuple[List[FeatureRow], str]:
    if path is None:
        return [], ""
    headers, raw_rows = csv_rows(path, ("feature", "effect", "significance"), "Feature CSV")
    supplied_classes = [row.get("significance_class", "") for _line, row in raw_rows]
    has_supplied_classes = any(supplied_classes)
    if has_supplied_classes and not all(supplied_classes):
        raise ContractError("significance_class must be supplied for every feature row or none.")
    if has_supplied_classes and effect_threshold is not None:
        raise ContractError("Do not combine supplied significance_class with threshold-derived classes.")

    rows: List[FeatureRow] = []
    seen = set()
    for line, raw in raw_rows:
        feature = raw["feature"]
        if not feature:
            raise ContractError(f"Line {line}: feature must not be blank.")
        if feature in seen:
            raise ContractError(f"Line {line}: duplicate feature {feature!r}.")
        seen.add(feature)
        effect = finite_number(raw["effect"], "effect", line)
        significance = finite_number(raw["significance"], "significance", line)
        assert effect is not None and significance is not None
        if not 0 < significance <= 1:
            raise ContractError(f"Line {line}: significance must lie in (0, 1].")
        if has_supplied_classes:
            category = raw["significance_class"]
        elif effect_threshold is not None and significance_threshold is not None:
            if significance <= significance_threshold and effect >= effect_threshold:
                category = "Threshold: positive"
            elif significance <= significance_threshold and effect <= -effect_threshold:
                category = "Threshold: negative"
            else:
                category = "Threshold: other"
        else:
            category = "Unclassified"
        rows.append(
            FeatureRow(
                line, feature, effect, significance, category,
                raw.get("data_status", "").upper(), raw.get("simulation_seed", "")
            )
        )
    if len(ordered_unique(row.category for row in rows)) > 12:
        raise ContractError("Feature classification has more than 12 categories; consolidate upstream.")
    if has_supplied_classes:
        class_note = "Feature classes are supplied upstream and plotted verbatim"
    elif effect_threshold is not None:
        class_note = (
            f"Feature classes use explicit display thresholds: |effect| >= {effect_threshold:g} "
            f"and significance <= {significance_threshold:g}"
        )
    else:
        class_note = "No feature significance classes supplied; all points are unclassified"
    return rows, class_note


def read_curves(path: Optional[Path]) -> Tuple[List[CurveRow], List[str]]:
    if path is None:
        return [], []
    _headers, raw_rows = csv_rows(path, ("curve_id", "rank", "running_score"), "Ranked curve CSV")
    rows: List[CurveRow] = []
    for line, raw in raw_rows:
        curve = raw["curve_id"]
        if not curve:
            raise ContractError(f"Line {line}: curve_id must not be blank.")
        rank = positive_integer(raw["rank"], "rank", line)
        score = finite_number(raw["running_score"], "running_score", line)
        assert rank is not None and score is not None
        rows.append(CurveRow(line, curve, rank, score, raw.get("data_status", "").upper(), raw.get("simulation_seed", "")))
    curves = ordered_unique(row.curve_id for row in rows)
    if len(curves) > MAX_CURVES:
        raise ContractError(f"At most {MAX_CURVES} precomputed curves can share one panel; split the figure.")
    for curve in curves:
        subset = [row for row in rows if row.curve_id == curve]
        if len(subset) < 2:
            raise ContractError(f"Curve {curve!r} needs at least two supplied coordinates.")
        ranks = [row.rank for row in subset]
        if any(current <= previous for previous, current in zip(ranks, ranks[1:])):
            raise ContractError(f"Curve {curve!r} ranks must appear in strictly increasing order.")
    return rows, curves


def read_hits(
    path: Optional[Path], curves: Sequence[CurveRow], curve_ids: Sequence[str]
) -> List[HitRow]:
    if path is None:
        return []
    _headers, raw_rows = csv_rows(path, ("curve_id", "rank"), "Hit CSV")
    known = set(curve_ids)
    valid_ranks = {
        curve: {row.rank for row in curves if row.curve_id == curve} for curve in curve_ids
    }
    rows: List[HitRow] = []
    seen = set()
    for line, raw in raw_rows:
        curve = raw["curve_id"]
        if curve not in known:
            raise ContractError(f"Hit line {line}: unknown curve_id {curve!r}.")
        rank = positive_integer(raw["rank"], "rank", line)
        assert rank is not None
        if rank not in valid_ranks[curve]:
            raise ContractError(f"Hit line {line}: rank is not a supplied coordinate for {curve!r}.")
        key = (curve, rank)
        if key in seen:
            raise ContractError(f"Hit line {line}: duplicate curve_id/rank pair.")
        seen.add(key)
        rows.append(HitRow(line, curve, rank, raw.get("data_status", "").upper(), raw.get("simulation_seed", "")))
    return rows


def read_summary(
    path: Optional[Path], curve_ids: Sequence[str], hits: Sequence[HitRow]
) -> List[SummaryRow]:
    if path is None:
        return []
    _headers, raw_rows = csv_rows(path, ("curve_id", "enrichment_score"), "Summary CSV")
    known = set(curve_ids)
    rows: List[SummaryRow] = []
    seen = set()
    for line, raw in raw_rows:
        curve = raw["curve_id"]
        if curve not in known:
            raise ContractError(f"Summary line {line}: unknown curve_id {curve!r}.")
        if curve in seen:
            raise ContractError(f"Summary line {line}: duplicate curve_id {curve!r}.")
        seen.add(curve)
        score = finite_number(raw["enrichment_score"], "enrichment_score", line)
        p_value = finite_number(raw.get("p_value", ""), "p_value", line, allow_blank=True)
        adjusted = finite_number(
            raw.get("adjusted_p_value", ""), "adjusted_p_value", line, allow_blank=True
        )
        for field, value in (("p_value", p_value), ("adjusted_p_value", adjusted)):
            if value is not None and not 0 <= value <= 1:
                raise ContractError(f"Summary line {line}: {field} must lie in [0, 1].")
        hit_count = positive_integer(raw.get("hit_count", ""), "hit_count", line, allow_blank=True)
        if hit_count is not None and hits:
            actual = sum(hit.curve_id == curve for hit in hits)
            if hit_count != actual:
                raise ContractError(
                    f"Summary line {line}: supplied hit_count={hit_count} but hit file has {actual}."
                )
        assert score is not None
        rows.append(
            SummaryRow(
                line, curve, score, p_value, adjusted, hit_count,
                raw.get("data_status", "").upper(), raw.get("simulation_seed", "")
            )
        )
    missing = set(curve_ids) - seen
    if missing:
        raise ContractError("Summary CSV must contain one row per curve; missing: " + ", ".join(sorted(missing)))
    return rows


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


def summary_text(row: SummaryRow) -> str:
    parts = [f"score={row.enrichment_score:.3g}"]
    if row.p_value is not None:
        parts.append(f"p={row.p_value:.3g}")
    if row.adjusted_p_value is not None:
        parts.append(f"adjusted={row.adjusted_p_value:.3g}")
    if row.hit_count is not None:
        parts.append(f"hits={row.hit_count}")
    return f"{row.curve_id}: " + ", ".join(parts)


def render(
    features: Sequence[FeatureRow],
    class_note: str,
    curves: Sequence[CurveRow],
    curve_ids: Sequence[str],
    hits: Sequence[HitRow],
    summaries: Sequence[SummaryRow],
    note: str,
    output_prefix: Path,
    title: str,
    effect_threshold: Optional[float],
    significance_threshold: Optional[float],
    dpi: int,
) -> Tuple[Path, Path]:
    panel_count = int(bool(features)) + int(bool(curves))
    figure, axes = plt.subplots(
        1, panel_count,
        figsize=((8.4 if panel_count == 1 else 14.8), 6.3),
        squeeze=False,
        facecolor=BACKGROUND,
    )
    figure.subplots_adjust(left=0.08, right=0.97, top=0.78, bottom=0.22, wspace=0.28)
    axis_index = 0
    if features:
        axis = axes[0, axis_index]; axis_index += 1
        categories = ordered_unique(row.category for row in features)
        category_colors = {
            category: COLORS[index % len(COLORS)] for index, category in enumerate(categories)
        }
        for category in categories:
            subset = [row for row in features if row.category == category]
            axis.scatter(
                [row.effect for row in subset],
                [-math.log10(row.significance) for row in subset],
                s=24, color=category_colors[category], alpha=0.72,
                edgecolor="white", linewidth=0.35, label=category,
            )
        axis.axvline(0, color="#657177", linewidth=0.8)
        if effect_threshold is not None and significance_threshold is not None:
            axis.axvline(effect_threshold, color="#747D80", linestyle="--", linewidth=0.8)
            axis.axvline(-effect_threshold, color="#747D80", linestyle="--", linewidth=0.8)
            axis.axhline(-math.log10(significance_threshold), color="#747D80", linestyle="--", linewidth=0.8)
        axis.set_xlabel("Supplied feature effect")
        axis.set_ylabel("-log10(supplied significance)")
        axis.set_title("Feature-level supplied statistics", loc="left", fontsize=11.5, fontweight="bold", pad=25)
        axis.text(0.0, 1.02, class_note, transform=axis.transAxes, ha="left", va="bottom", fontsize=7.3, color=MUTED)
        axis.legend(frameon=False, fontsize=7.4, loc="best")
        axis.grid(color=GRID, linewidth=0.65)
        axis.set_axisbelow(True)
        for spine in ("top", "right"):
            axis.spines[spine].set_visible(False)

    if curves:
        axis = axes[0, axis_index]
        curve_colors = {
            curve: COLORS[index % len(COLORS)] for index, curve in enumerate(curve_ids)
        }
        for curve in curve_ids:
            subset = [row for row in curves if row.curve_id == curve]
            axis.plot(
                [row.rank for row in subset],
                [row.running_score for row in subset],
                color=curve_colors[curve], linewidth=1.8, label=curve,
            )
        axis.axhline(0, color="#657177", linewidth=0.8)
        if hits:
            transform = axis.get_xaxis_transform()
            for index, curve in enumerate(curve_ids):
                ranks = [row.rank for row in hits if row.curve_id == curve]
                if ranks:
                    lower = 0.02 + 0.025 * index
                    axis.vlines(
                        ranks, lower, lower + 0.016,
                        transform=transform, color=curve_colors[curve], linewidth=0.8, alpha=0.85
                    )
        axis.set_xlabel("Supplied rank position")
        axis.set_ylabel("Precomputed running enrichment score")
        axis.set_title("Precomputed ranked enrichment curves", loc="left", fontsize=11.5, fontweight="bold", pad=25)
        axis.text(
            0.0, 1.02,
            "Curves and hit positions are supplied/precomputed; no enrichment algorithm is run",
            transform=axis.transAxes, ha="left", va="bottom", fontsize=7.3, color=MUTED,
        )
        axis.legend(frameon=False, fontsize=7.6, loc="best")
        if summaries:
            axis.text(
                0.0, -0.25,
                "SUPPLIED SUMMARY · " + " | ".join(summary_text(row) for row in summaries),
                transform=axis.transAxes, ha="left", va="top", fontsize=6.6, color=INK,
                clip_on=False,
                bbox={"facecolor": BACKGROUND, "edgecolor": "#D5D2CB", "alpha": 0.92, "pad": 4},
            )
        axis.grid(color=GRID, linewidth=0.65)
        axis.set_axisbelow(True)
        for spine in ("top", "right"):
            axis.spines[spine].set_visible(False)

    figure.text(0.035, 0.975, title, ha="left", va="top", fontsize=18, fontweight="bold", color=INK)
    figure.text(0.035, 0.928, note, ha="left", va="top", fontsize=9.0, color=MUTED)
    figure.text(
        0.035, 0.890,
        "All feature statistics, classes, ranked curves, hit positions, and summaries are supplied or explicitly threshold-derived display fields; no GSEA/pathway query is performed.",
        ha="left", va="top", fontsize=8.0, color=MUTED,
    )
    figure.text(
        0.035, 0.025,
        "The plot does not validate pathway provenance, multiple-testing procedure, ranking construction, or statistical significance. Interpretation remains upstream.",
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
    parser = argparse.ArgumentParser(description="Visualize supplied feature statistics and precomputed enrichment outputs.")
    parser.add_argument("--features", type=Path)
    parser.add_argument("--curve", type=Path)
    parser.add_argument("--hits", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--effect-threshold", type=float)
    parser.add_argument("--significance-threshold", type=float)
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT_PREFIX)
    parser.add_argument("--title", default="Supplied feature and precomputed enrichment views")
    parser.add_argument("--dpi", type=int, default=320)
    args = parser.parse_args()
    supplied_any = any(path is not None for path in (args.features, args.curve, args.hits, args.summary))
    if not supplied_any:
        args.features = DEMO_FEATURES
        args.curve = DEMO_CURVES
        args.hits = DEMO_HITS
        args.summary = DEMO_SUMMARY
    if args.hits is not None and args.curve is None:
        parser.error("--hits requires --curve.")
    if args.summary is not None and args.curve is None:
        parser.error("--summary requires --curve.")
    if args.features is None and args.curve is None:
        parser.error("Provide --features, --curve, or both.")
    if (args.effect_threshold is None) != (args.significance_threshold is None):
        parser.error("Provide --effect-threshold and --significance-threshold together.")
    if args.effect_threshold is not None and args.effect_threshold <= 0:
        parser.error("--effect-threshold must be > 0.")
    if args.significance_threshold is not None and not 0 < args.significance_threshold <= 1:
        parser.error("--significance-threshold must lie in (0, 1].")
    if args.dpi < 150:
        parser.error("--dpi must be at least 150.")
    return args


def main() -> int:
    args = parse_args()
    try:
        features, class_note = read_features(
            args.features.expanduser() if args.features else None,
            args.effect_threshold,
            args.significance_threshold,
        )
        curves, curve_ids = read_curves(args.curve.expanduser() if args.curve else None)
        hits = read_hits(args.hits.expanduser() if args.hits else None, curves, curve_ids)
        summaries = read_summary(
            args.summary.expanduser() if args.summary else None, curve_ids, hits
        )
        note = metadata_note((features, curves, hits, summaries))
        png_path, svg_path = render(
            features, class_note, curves, curve_ids, hits, summaries, note,
            args.output_prefix, args.title, args.effect_threshold,
            args.significance_threshold, args.dpi,
        )
    except ContractError as exc:
        raise SystemExit(f"Input validation failed: {exc}") from exc
    panels = []
    if features:
        panels.append(f"feature panel={len(features)} rows")
    if curves:
        panels.append(
            f"enrichment panel={len(curves)} curve coordinates, {len(hits)} hits, "
            f"{len(summaries)} summaries"
        )
    print("Validated " + "; ".join(panels))
    print(f"Data status: {note}")
    print(f"PNG: {png_path.resolve()}")
    print(f"SVG: {svg_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
