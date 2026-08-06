#!/usr/bin/env python3
"""Render identity-preserving change between exactly two timepoints."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional


PACK_DIR = Path(__file__).resolve().parent
SHARED_DIR = PACK_DIR.parent / "_shared"
sys.path.insert(0, str(SHARED_DIR))

from runtime import (  # noqa: E402
    bind_category_order,
    bind_figure_contract,
    configure_matplotlib,
    exact_order,
    load_data_manifest,
    parse_formats,
    quantile,
    split_list,
    write_bundle,
)


IMPLEMENTATION_ID = "paired-change-v1"
IMPLEMENTATION_VERSION = "1.0.0"
CHECK = "PC"
DEFAULT_COLORS = [
    "#3B82A0",
    "#D97941",
    "#4D9B77",
    "#9A6FB0",
    "#C6A23A",
    "#6E7F91",
]


def read_and_validate(args: argparse.Namespace) -> dict[str, Any]:
    input_path = args.input.resolve()
    if not input_path.is_file():
        raise ValueError(f"{CHECK}-INPUT-01 input file not found: {input_path}")
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        if len(fieldnames) != len(set(fieldnames)):
            raise ValueError(f"{CHECK}-INPUT-01 duplicate CSV column names")
        required = {
            args.subject_col,
            args.group_col,
            args.timepoint_col,
            args.value_col,
        }
        if args.run_mode == "smoke":
            required.add("source_type")
        missing = sorted(required - set(fieldnames))
        if missing:
            raise ValueError(
                f"{CHECK}-INPUT-01 missing required columns: {missing}"
            )
        raw_rows = list(reader)
    if not raw_rows:
        raise ValueError(f"{CHECK}-INPUT-01 input contains no data rows")

    by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
    observed_groups: list[str] = []
    observed_timepoints: list[str] = []
    seen_keys: set[tuple[str, str]] = set()
    for row_number, row in enumerate(raw_rows, start=2):
        subject = (row.get(args.subject_col) or "").strip()
        group = (row.get(args.group_col) or "").strip()
        timepoint = (row.get(args.timepoint_col) or "").strip()
        raw_value = (row.get(args.value_col) or "").strip()
        if not subject or not group or not timepoint or not raw_value:
            raise ValueError(
                f"{CHECK}-INPUT-01 blank required value at CSV row {row_number}"
            )
        key = (subject, timepoint)
        if key in seen_keys:
            raise ValueError(
                f"{CHECK}-KEY-01 duplicate subject-timepoint key {key!r}"
            )
        seen_keys.add(key)
        try:
            value = float(raw_value)
        except ValueError as exc:
            raise ValueError(
                f"{CHECK}-VALUE-01 nonnumeric value at CSV row {row_number}"
            ) from exc
        if not math.isfinite(value):
            raise ValueError(
                f"{CHECK}-VALUE-01 nonfinite value at CSV row {row_number}"
            )
        if args.run_mode == "smoke" and (
            row.get("source_type") or ""
        ).strip() != "simulated":
            raise ValueError(
                f"{CHECK}-DEMO-01 smoke rows require source_type=simulated"
            )
        if args.run_mode == "production" and (
            row.get("source_type") or ""
        ).strip().lower() in {"simulated", "synthetic", "demo"}:
            raise ValueError(
                f"{CHECK}-DEMO-01 synthetic/demo rows cannot be used in production"
            )
        if group not in observed_groups:
            observed_groups.append(group)
        if timepoint not in observed_timepoints:
            observed_timepoints.append(timepoint)
        by_subject[subject].append(
            {
                "subject": subject,
                "group": group,
                "timepoint": timepoint,
                "value": value,
            }
        )

    timepoints = exact_order(
        "timepoint order",
        split_list(args.timepoint_order),
        observed_timepoints,
        check_id=f"{CHECK}-ORDER-01",
    )
    if len(timepoints) != 2:
        raise ValueError(
            f"{CHECK}-PAIR-01 exactly two timepoints are required; "
            f"observed {timepoints}"
        )
    groups = exact_order(
        "group order",
        split_list(args.group_order),
        observed_groups,
        check_id=f"{CHECK}-ORDER-01",
    )
    if len(groups) > len(DEFAULT_COLORS):
        raise ValueError(
            f"{CHECK}-ENCODE-01 at most {len(DEFAULT_COLORS)} groups are supported"
        )
    colors = split_list(args.colors) or DEFAULT_COLORS[: len(groups)]
    if len(colors) != len(groups):
        raise ValueError(
            f"{CHECK}-ENCODE-01 colors must match the declared group count"
        )

    pairs: list[dict[str, Any]] = []
    expected_timepoints = set(timepoints)
    for subject, rows in by_subject.items():
        groups_for_subject = {row["group"] for row in rows}
        if len(groups_for_subject) != 1:
            raise ValueError(
                f"{CHECK}-GROUP-01 subject {subject!r} changes group"
            )
        actual_timepoints = {row["timepoint"] for row in rows}
        if actual_timepoints != expected_timepoints:
            raise ValueError(
                f"{CHECK}-PAIR-01 subject {subject!r} is not a complete pair; "
                f"expected={timepoints}, observed={sorted(actual_timepoints)}"
            )
        value_by_timepoint = {
            row["timepoint"]: row["value"] for row in rows
        }
        start = value_by_timepoint[timepoints[0]]
        end = value_by_timepoint[timepoints[1]]
        pairs.append(
            {
                "subject": subject,
                "group": next(iter(groups_for_subject)),
                "start": start,
                "end": end,
                "change": end - start,
            }
        )
    if any(not any(pair["group"] == group for pair in pairs) for group in groups):
        raise ValueError(f"{CHECK}-GROUP-01 every declared group needs a pair")
    return {
        "pairs": pairs,
        "groups": groups,
        "colors": colors,
        "timepoints": timepoints,
        "rows_read": len(raw_rows),
    }


def render(
    args: argparse.Namespace,
    data: dict[str, Any],
    formats: list[str],
    data_manifest: dict[str, Any],
    figure_contract: Optional[dict[str, Any]],
) -> dict[str, Any]:
    matplotlib, plt = configure_matplotlib(IMPLEMENTATION_ID)
    width_in = args.width_mm / 25.4
    height_in = args.height_mm / 25.4
    fig, axes_grid = plt.subplots(
        1,
        len(data["groups"]),
        figsize=(width_in, height_in),
        dpi=args.dpi,
        sharey=True,
        squeeze=False,
        gridspec_kw={"wspace": 0.10},
    )
    axes = list(axes_grid[0])
    fig.subplots_adjust(left=0.11, right=0.97, bottom=0.20, top=0.76)
    fig.text(
        0.11,
        0.94,
        args.title,
        ha="left",
        va="top",
        fontsize=15,
        fontweight="bold",
        color="#17212B",
    )
    if args.subtitle:
        fig.text(
            0.11,
            0.875,
            args.subtitle,
            ha="left",
            va="top",
            fontsize=9.5,
            color="#64707B",
        )

    analysis_rows: list[dict[str, Any]] = []
    for group_index, (axis, group, color) in enumerate(
        zip(axes, data["groups"], data["colors"])
    ):
        group_pairs = [
            pair for pair in data["pairs"] if pair["group"] == group
        ]
        for pair in group_pairs:
            axis.plot(
                [0, 1],
                [pair["start"], pair["end"]],
                color=color,
                linewidth=1.15,
                alpha=0.58,
                zorder=2,
            )
            axis.scatter(
                [0, 1],
                [pair["start"], pair["end"]],
                s=26,
                facecolor=color,
                edgecolor="white",
                linewidth=0.5,
                zorder=3,
            )
            analysis_rows.append(
                {
                    "subject": pair["subject"],
                    "group": group,
                    "start_timepoint": data["timepoints"][0],
                    "start_value": f"{pair['start']:.17g}",
                    "end_timepoint": data["timepoints"][1],
                    "end_value": f"{pair['end']:.17g}",
                    "change_end_minus_start": f"{pair['change']:.17g}",
                }
            )
        median_change = quantile(
            [pair["change"] for pair in group_pairs],
            0.5,
        )
        axis.set_title(
            f"{group}  ·  n={len(group_pairs)}",
            fontsize=10.5,
            fontweight="bold",
            pad=9,
        )
        axis.text(
            0.5,
            0.99,
            f"Median Δ = {median_change:.3g}",
            transform=axis.transAxes,
            ha="center",
            va="top",
            fontsize=8,
            color="#64707B",
        )
        axis.set_xticks([0, 1], data["timepoints"])
        axis.set_xlim(-0.25, 1.25)
        axis.grid(axis="y", color="#E4E8EB", linewidth=0.65)
        axis.set_axisbelow(True)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.spines["bottom"].set_color("#34404A")
        if group_index == 0:
            axis.spines["left"].set_color("#34404A")
            axis.set_ylabel(args.y_label, fontsize=10)
        else:
            axis.spines["left"].set_visible(False)
            axis.tick_params(axis="y", left=False, labelleft=False)
        axis.tick_params(labelsize=8.5)
    if args.run_mode == "smoke":
        fig.text(
            0.5,
            0.035,
            "SYNTHETIC SMOKE TEST — NOT SCIENTIFIC EVIDENCE",
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="bold",
            color="#B42318",
        )

    checks = [
        {
            "id": f"{CHECK}-INPUT-01",
            "status": "PASS",
            "evidence": "required columns and nonblank rows validated",
        },
        {
            "id": f"{CHECK}-KEY-01",
            "status": "PASS",
            "evidence": "subject-timepoint keys are unique",
        },
        {
            "id": f"{CHECK}-PAIR-01",
            "status": "PASS",
            "evidence": "every subject has exactly the two declared timepoints",
        },
        {
            "id": f"{CHECK}-GROUP-01",
            "status": "PASS",
            "evidence": "group is constant within subject",
        },
        {
            "id": f"{CHECK}-VALUE-01",
            "status": "PASS",
            "evidence": "all paired values and derived changes are finite",
        },
        {
            "id": f"{CHECK}-DEMO-01",
            "status": "PASS",
            "evidence": "data role and smoke watermark are explicit",
        },
    ]
    return write_bundle(
        fig=fig,
        matplotlib=matplotlib,
        output_dir=args.output_dir.resolve(),
        basename="paired-change",
        formats=formats,
        dpi=args.dpi,
        width_mm=args.width_mm,
        height_mm=args.height_mm,
        title=args.title,
        implementation_id=IMPLEMENTATION_ID,
        implementation_version=IMPLEMENTATION_VERSION,
        source_files={
            "render.py": Path(__file__).resolve(),
            "implementations/python/_shared/runtime.py": (
                SHARED_DIR / "runtime.py"
            ).resolve(),
        },
        input_paths=[args.input.resolve()],
        data_manifest=data_manifest,
        figure_contract=figure_contract,
        run_mode=args.run_mode,
        rows_read=data["rows_read"],
        rows_included=data["rows_read"],
        field_mapping={
            "subject": args.subject_col,
            "group": args.group_col,
            "timepoint": args.timepoint_col,
            "value": args.value_col,
        },
        analysis_unit="one declared subject",
        replicate_unit="one declared subject",
        analysis_fieldnames=[
            "subject",
            "group",
            "start_timepoint",
            "start_value",
            "end_timepoint",
            "end_value",
            "change_end_minus_start",
        ],
        analysis_rows=analysis_rows,
        validation_checks=checks,
        data_details={
            "group_order": data["groups"],
            "timepoint_order": data["timepoints"],
            "complete_pairs": len(data["pairs"]),
            "change_definition": (
                f"{data['timepoints'][1]} minus {data['timepoints'][0]}"
            ),
        },
        figure_details={
            "group_order": data["groups"],
            "timepoint_order": data["timepoints"],
            "identity_preserved": True,
            "watermark": args.run_mode == "smoke",
        },
        scientific_scope={
            "supports": [
                "identity-preserving two-timepoint change",
                "descriptive within-group median change",
            ],
            "does_not_compute": [
                "between-group effect estimates",
                "confidence intervals",
                "hypothesis tests",
                "causal effects",
            ],
        },
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Render exactly two complete observations per subject. "
            "No inferential statistics are computed."
        )
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--data-manifest", type=Path, required=True)
    parser.add_argument("--figure-contract", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--run-mode", choices=("smoke", "production"), required=True
    )
    parser.add_argument("--subject-col", default="subject")
    parser.add_argument("--group-col", default="group")
    parser.add_argument("--timepoint-col", default="timepoint")
    parser.add_argument("--value-col", default="value")
    parser.add_argument("--group-order")
    parser.add_argument("--timepoint-order", required=True)
    parser.add_argument("--colors")
    parser.add_argument("--title", default="Paired change by group")
    parser.add_argument(
        "--subtitle",
        default="Each line is one declared subject; Δ is end minus start",
    )
    parser.add_argument("--y-label", default="Measured value (declared units)")
    parser.add_argument("--formats", default="svg,pdf,png")
    parser.add_argument("--width-mm", type=float, default=183)
    parser.add_argument("--height-mm", type=float, default=105)
    parser.add_argument("--dpi", type=int, default=300)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.width_mm <= 0 or args.height_mm <= 0 or args.dpi <= 0:
            raise ValueError(f"{CHECK}-OUTPUT-01 dimensions and DPI must be positive")
        formats = parse_formats(args.formats)
        data_manifest = load_data_manifest(
            args.data_manifest,
            [args.input],
            args.run_mode,
            check_id=f"{CHECK}-DEMO-01",
            bundled_demo_paths=[PACK_DIR / "examples" / "demo.csv"],
            semantic_column_bindings={
                "subject": args.subject_col,
                "group": args.group_col,
                "timepoint": args.timepoint_col,
                "value": args.value_col,
            },
            numeric_semantic_roles={"value"},
        )
        data = read_and_validate(args)
        if args.run_mode == "production" and args.figure_contract is None:
            raise ValueError(
                f"{CHECK}-CONTRACT-01 production requires --figure-contract"
            )
        figure_contract = (
            bind_figure_contract(
                args.figure_contract,
                implementation_id=IMPLEMENTATION_ID,
                implementation_version=IMPLEMENTATION_VERSION,
                supported_phases={"descriptive", "exploratory", "presentation"},
                run_mode=args.run_mode,
                formats=formats,
                width_mm=args.width_mm,
                height_mm=args.height_mm,
                dpi=args.dpi,
                included_rows=data["rows_read"],
                check_id=f"{CHECK}-CONTRACT-01",
            )
            if args.figure_contract
            else None
        )
        if figure_contract:
            bind_category_order(
                figure_contract,
                "group",
                data["groups"],
                check_id=f"{CHECK}-CONTRACT-01",
            )
            bind_category_order(
                figure_contract,
                "timepoint",
                data["timepoints"],
                check_id=f"{CHECK}-CONTRACT-01",
            )
        manifest = render(
            args,
            data,
            formats,
            data_manifest,
            figure_contract,
        )
    except (OSError, ValueError, RuntimeError, csv.Error) as exc:
        print(f"{IMPLEMENTATION_ID}: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "rendered",
                "implementation": IMPLEMENTATION_ID,
                "manifest": str(
                    args.output_dir.resolve() / "paired-change.manifest.json"
                ),
                "artifacts": [
                    item["file"] for item in manifest["artifacts"]
                ],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
