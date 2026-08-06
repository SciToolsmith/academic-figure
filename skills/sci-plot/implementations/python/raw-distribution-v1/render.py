#!/usr/bin/env python3
"""Render raw observations with a descriptive median and interquartile range."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional


PACK_DIR = Path(__file__).resolve().parent
SHARED_DIR = PACK_DIR.parent / "_shared"
sys.path.insert(0, str(SHARED_DIR))

from runtime import (  # noqa: E402
    bind_category_order,
    bind_figure_contract,
    configure_matplotlib,
    deterministic_offset,
    exact_order,
    load_data_manifest,
    parse_formats,
    quantile,
    split_list,
    write_bundle,
)


IMPLEMENTATION_ID = "raw-distribution-v1"
IMPLEMENTATION_VERSION = "1.0.0"
CHECK = "RD"
DEFAULT_COLORS = [
    "#3B82A0",
    "#D97941",
    "#4D9B77",
    "#9A6FB0",
    "#C6A23A",
    "#6E7F91",
    "#B45F72",
    "#5C8DC4",
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
            args.observation_col,
            args.group_col,
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

    records: list[dict[str, Any]] = []
    observed_groups: list[str] = []
    seen_observations: set[str] = set()
    for row_number, row in enumerate(raw_rows, start=2):
        observation = (row.get(args.observation_col) or "").strip()
        group = (row.get(args.group_col) or "").strip()
        raw_value = (row.get(args.value_col) or "").strip()
        if not observation or not group or not raw_value:
            raise ValueError(
                f"{CHECK}-INPUT-01 blank required value at CSV row {row_number}"
            )
        if observation in seen_observations:
            raise ValueError(
                f"{CHECK}-KEY-01 duplicate observation id {observation!r}"
            )
        seen_observations.add(observation)
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
        records.append(
            {
                "observation_id": observation,
                "group": group,
                "value": value,
            }
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
    counts = Counter(record["group"] for record in records)
    undersized = {group: counts[group] for group in groups if counts[group] < 2}
    if undersized:
        raise ValueError(
            f"{CHECK}-SUMMARY-01 median and IQR require at least two "
            f"observations per group; found {undersized}"
        )
    colors = split_list(args.colors) or DEFAULT_COLORS[: len(groups)]
    if len(colors) != len(groups):
        raise ValueError(
            f"{CHECK}-ENCODE-01 colors must match the declared group count"
        )
    values_by_group = {
        group: [
            record["value"] for record in records if record["group"] == group
        ]
        for group in groups
    }
    return {
        "records": records,
        "groups": groups,
        "colors": colors,
        "values_by_group": values_by_group,
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
    fig, axis = plt.subplots(
        1,
        1,
        figsize=(width_in, height_in),
        dpi=args.dpi,
    )
    fig.subplots_adjust(left=0.12, right=0.97, bottom=0.20, top=0.78)
    fig.text(
        0.12,
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
            0.12,
            0.875,
            args.subtitle,
            ha="left",
            va="top",
            fontsize=9.5,
            color="#64707B",
        )

    analysis_rows: list[dict[str, Any]] = []
    for group_index, (group, color) in enumerate(
        zip(data["groups"], data["colors"])
    ):
        group_records = [
            record for record in data["records"] if record["group"] == group
        ]
        values = data["values_by_group"][group]
        q1 = quantile(values, 0.25)
        median = quantile(values, 0.50)
        q3 = quantile(values, 0.75)
        x_values = [
            group_index + deterministic_offset(record["observation_id"])
            for record in group_records
        ]
        axis.scatter(
            x_values,
            values,
            s=30,
            facecolor=color,
            edgecolor="white",
            linewidth=0.55,
            alpha=0.88,
            zorder=3,
        )
        axis.vlines(
            group_index,
            q1,
            q3,
            color="#17212B",
            linewidth=2.2,
            zorder=4,
        )
        axis.hlines(
            median,
            group_index - 0.22,
            group_index + 0.22,
            color="#17212B",
            linewidth=2.4,
            zorder=5,
        )
        for record in group_records:
            analysis_rows.append(
                {
                    "observation_id": record["observation_id"],
                    "group": group,
                    "value": f"{record['value']:.17g}",
                    "group_n": len(values),
                    "group_q1": f"{q1:.17g}",
                    "group_median": f"{median:.17g}",
                    "group_q3": f"{q3:.17g}",
                }
            )

    axis.set_xticks(
        range(len(data["groups"])),
        [
            f"{group}\n(n={len(data['values_by_group'][group])})"
            for group in data["groups"]
        ],
    )
    axis.set_xlim(-0.55, len(data["groups"]) - 0.45)
    axis.set_ylabel(args.y_label, fontsize=10)
    axis.grid(axis="y", color="#E4E8EB", linewidth=0.65)
    axis.set_axisbelow(True)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.spines["left"].set_color("#34404A")
    axis.spines["bottom"].set_color("#34404A")
    axis.tick_params(labelsize=8.5)
    axis.text(
        0.995,
        1.02,
        "Median · IQR",
        transform=axis.transAxes,
        ha="right",
        va="bottom",
        fontsize=8,
        color="#64707B",
    )
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
            "evidence": "observation identifiers are globally unique",
        },
        {
            "id": f"{CHECK}-VALUE-01",
            "status": "PASS",
            "evidence": "all plotted values are finite",
        },
        {
            "id": f"{CHECK}-ORDER-01",
            "status": "PASS",
            "evidence": "declared group order exactly covers observed groups",
        },
        {
            "id": f"{CHECK}-SUMMARY-01",
            "status": "PASS",
            "evidence": "median and IQR are descriptive and group-local",
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
        basename="distribution",
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
        rows_included=len(data["records"]),
        field_mapping={
            "observation_id": args.observation_col,
            "group": args.group_col,
            "value": args.value_col,
        },
        analysis_unit="one declared observation",
        replicate_unit="one declared observation",
        analysis_fieldnames=[
            "observation_id",
            "group",
            "value",
            "group_n",
            "group_q1",
            "group_median",
            "group_q3",
        ],
        analysis_rows=analysis_rows,
        validation_checks=checks,
        data_details={
            "group_order": data["groups"],
            "summary": "median and linear-interpolated interquartile range",
        },
        figure_details={
            "group_order": data["groups"],
            "point_jitter": "deterministic SHA-256 offset by observation id",
            "summary_geometry": "median line and IQR interval",
            "watermark": args.run_mode == "smoke",
        },
        scientific_scope={
            "supports": [
                "raw distribution inspection",
                "descriptive median and interquartile range",
            ],
            "does_not_compute": [
                "confidence intervals",
                "hypothesis tests",
                "causal effects",
            ],
        },
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Render raw observations with descriptive median and IQR. "
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
    parser.add_argument("--observation-col", default="observation_id")
    parser.add_argument("--group-col", default="group")
    parser.add_argument("--value-col", default="value")
    parser.add_argument("--group-order")
    parser.add_argument("--colors")
    parser.add_argument("--title", default="Raw distributions by group")
    parser.add_argument(
        "--subtitle",
        default="Every point is one declared observation; summary is median · IQR",
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
                "observation_id": args.observation_col,
                "group": args.group_col,
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
                included_rows=len(data["records"]),
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
                    args.output_dir.resolve() / "distribution.manifest.json"
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
