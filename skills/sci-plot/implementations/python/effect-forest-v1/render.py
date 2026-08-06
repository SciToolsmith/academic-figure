#!/usr/bin/env python3
"""Render declared, precomputed effect estimates and intervals."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any, Optional


PACK_DIR = Path(__file__).resolve().parent
SHARED_DIR = PACK_DIR.parent / "_shared"
sys.path.insert(0, str(SHARED_DIR))

from runtime import (  # noqa: E402
    bind_category_order,
    bind_figure_contract,
    bind_native_semantics,
    configure_matplotlib,
    exact_order,
    load_data_manifest,
    parse_formats,
    split_list,
    write_bundle,
)


IMPLEMENTATION_ID = "effect-forest-v1"
IMPLEMENTATION_VERSION = "1.0.0"
CHECK = "EF"
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
            args.label_col,
            args.group_col,
            args.estimate_col,
            args.lower_col,
            args.upper_col,
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
    if len(raw_rows) > args.max_rows:
        raise ValueError(
            f"{CHECK}-ENCODE-01 {len(raw_rows)} rows exceed --max-rows "
            f"{args.max_rows}; split the evidence architecture"
        )

    records: list[dict[str, Any]] = []
    labels: list[str] = []
    groups: list[str] = []
    for row_number, row in enumerate(raw_rows, start=2):
        label = (row.get(args.label_col) or "").strip()
        group = (row.get(args.group_col) or "").strip()
        if not label or not group:
            raise ValueError(
                f"{CHECK}-INPUT-01 blank label or group at CSV row {row_number}"
            )
        if label in labels:
            raise ValueError(f"{CHECK}-KEY-01 duplicate label {label!r}")
        numbers: dict[str, float] = {}
        for role, column in (
            ("estimate", args.estimate_col),
            ("lower", args.lower_col),
            ("upper", args.upper_col),
        ):
            raw_value = (row.get(column) or "").strip()
            try:
                value = float(raw_value)
            except ValueError as exc:
                raise ValueError(
                    f"{CHECK}-VALUE-01 nonnumeric {role} at CSV row {row_number}"
                ) from exc
            if not math.isfinite(value):
                raise ValueError(
                    f"{CHECK}-VALUE-01 nonfinite {role} at CSV row {row_number}"
                )
            numbers[role] = value
        if not (
            numbers["lower"] <= numbers["estimate"] <= numbers["upper"]
        ):
            raise ValueError(
                f"{CHECK}-INTERVAL-01 expected lower <= estimate <= upper "
                f"at CSV row {row_number}"
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
        labels.append(label)
        if group not in groups:
            groups.append(group)
        records.append(
            {
                "label": label,
                "group": group,
                **numbers,
            }
        )

    label_order = exact_order(
        "label order",
        split_list(args.label_order),
        labels,
        check_id=f"{CHECK}-ORDER-01",
    )
    group_order = exact_order(
        "group order",
        split_list(args.group_order),
        groups,
        check_id=f"{CHECK}-ORDER-01",
    )
    if len(group_order) > len(DEFAULT_COLORS):
        raise ValueError(
            f"{CHECK}-ENCODE-01 at most {len(DEFAULT_COLORS)} groups are supported"
        )
    colors = split_list(args.colors) or DEFAULT_COLORS[: len(group_order)]
    if len(colors) != len(group_order):
        raise ValueError(
            f"{CHECK}-ENCODE-01 colors must match the declared group count"
        )
    record_by_label = {record["label"]: record for record in records}
    return {
        "records": [record_by_label[label] for label in label_order],
        "label_order": label_order,
        "group_order": group_order,
        "colors": colors,
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
    from matplotlib.lines import Line2D

    width_in = args.width_mm / 25.4
    height_in = args.height_mm / 25.4
    fig, axis = plt.subplots(
        1,
        1,
        figsize=(width_in, height_in),
        dpi=args.dpi,
    )
    fig.subplots_adjust(left=0.31, right=0.96, bottom=0.20, top=0.70)
    fig.text(
        0.10,
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
            0.10,
            0.875,
            args.subtitle,
            ha="left",
            va="top",
            fontsize=9.5,
            color="#64707B",
        )

    color_by_group = dict(zip(data["group_order"], data["colors"]))
    y_by_label = {
        label: len(data["label_order"]) - index - 1
        for index, label in enumerate(data["label_order"])
    }
    for record in data["records"]:
        lower_error = record["estimate"] - record["lower"]
        upper_error = record["upper"] - record["estimate"]
        axis.errorbar(
            record["estimate"],
            y_by_label[record["label"]],
            xerr=[[lower_error], [upper_error]],
            fmt="o",
            markersize=5.8,
            markerfacecolor=color_by_group[record["group"]],
            markeredgecolor="white",
            markeredgewidth=0.6,
            ecolor=color_by_group[record["group"]],
            elinewidth=1.6,
            capsize=2.8,
            capthick=1.2,
            zorder=3,
        )
    axis.axvline(
        args.reference,
        color="#6B7280",
        linewidth=1.0,
        linestyle=(0, (4, 3)),
        zorder=1,
    )
    axis.set_yticks(
        [y_by_label[label] for label in data["label_order"]],
        data["label_order"],
    )
    axis.set_ylim(-0.7, len(data["label_order"]) - 0.3)
    axis.set_xlabel(args.x_label, fontsize=10)
    axis.grid(axis="x", color="#E4E8EB", linewidth=0.65)
    axis.set_axisbelow(True)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.spines["left"].set_visible(False)
    axis.spines["bottom"].set_color("#34404A")
    axis.tick_params(axis="y", length=0, labelsize=8.5)
    axis.tick_params(axis="x", labelsize=8.5)
    axis.text(
        0.995,
        1.02,
        f"Precomputed {args.interval_label}",
        transform=axis.transAxes,
        ha="right",
        va="bottom",
        fontsize=8,
        color="#64707B",
    )
    if len(data["group_order"]) > 1:
        handles = [
            Line2D(
                [],
                [],
                marker="o",
                linestyle="none",
                markersize=6,
                markerfacecolor=color_by_group[group],
                markeredgecolor="white",
                label=group,
            )
            for group in data["group_order"]
        ]
        fig.legend(
            handles=handles,
            loc="upper right",
            bbox_to_anchor=(0.96, 0.825),
            ncol=len(data["group_order"]),
            frameon=False,
            fontsize=8,
            columnspacing=1.1,
            handletextpad=0.35,
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

    analysis_rows = [
        {
            "label": record["label"],
            "group": record["group"],
            "estimate": f"{record['estimate']:.17g}",
            "lower": f"{record['lower']:.17g}",
            "upper": f"{record['upper']:.17g}",
            "effect_scale": args.effect_scale,
            "interval_definition": args.interval_label,
            "reference_value": f"{args.reference:.17g}",
        }
        for record in data["records"]
    ]
    checks = [
        {
            "id": f"{CHECK}-INPUT-01",
            "status": "PASS",
            "evidence": "required columns and nonblank labels validated",
        },
        {
            "id": f"{CHECK}-KEY-01",
            "status": "PASS",
            "evidence": "effect labels are globally unique",
        },
        {
            "id": f"{CHECK}-VALUE-01",
            "status": "PASS",
            "evidence": "all estimates and interval bounds are finite",
        },
        {
            "id": f"{CHECK}-INTERVAL-01",
            "status": "PASS",
            "evidence": "every estimate lies within its declared interval",
        },
        {
            "id": f"{CHECK}-ORDER-01",
            "status": "PASS",
            "evidence": "declared label and group orders exactly cover inputs",
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
        basename="effect-forest",
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
            "label": args.label_col,
            "group": args.group_col,
            "estimate": args.estimate_col,
            "lower": args.lower_col,
            "upper": args.upper_col,
        },
        analysis_unit="one declared precomputed estimate",
        replicate_unit="not applicable; input contains precomputed estimates",
        analysis_fieldnames=[
            "label",
            "group",
            "estimate",
            "lower",
            "upper",
            "effect_scale",
            "interval_definition",
            "reference_value",
        ],
        analysis_rows=analysis_rows,
        validation_checks=checks,
        data_details={
            "label_order": data["label_order"],
            "group_order": data["group_order"],
            "effect_scale": args.effect_scale,
            "interval_definition": args.interval_label,
            "reference_value": args.reference,
            "input_is_precomputed": True,
        },
        figure_details={
            "label_order": data["label_order"],
            "group_order": data["group_order"],
            "reference_value": args.reference,
            "watermark": args.run_mode == "smoke",
        },
        scientific_scope={
            "supports": [
                "presentation of declared precomputed point estimates",
                "presentation of declared precomputed intervals",
            ],
            "does_not_compute": [
                "effect estimates",
                "confidence or credible intervals",
                "p-values",
                "causal identification",
            ],
        },
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Render declared precomputed estimates and intervals. "
            "This implementation performs no statistical estimation."
        )
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--data-manifest", type=Path, required=True)
    parser.add_argument("--figure-contract", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--run-mode", choices=("smoke", "production"), required=True
    )
    parser.add_argument("--label-col", default="label")
    parser.add_argument("--group-col", default="group")
    parser.add_argument("--estimate-col", default="estimate")
    parser.add_argument("--lower-col", default="lower")
    parser.add_argument("--upper-col", default="upper")
    parser.add_argument("--label-order")
    parser.add_argument("--group-order")
    parser.add_argument("--colors")
    parser.add_argument("--effect-scale", required=True)
    parser.add_argument("--interval-label", required=True)
    parser.add_argument("--reference", type=float, default=0.0)
    parser.add_argument("--max-rows", type=int, default=30)
    parser.add_argument("--title", default="Effect estimates")
    parser.add_argument(
        "--subtitle",
        default="Points and intervals are declared precomputed results",
    )
    parser.add_argument("--x-label", default="Declared effect scale")
    parser.add_argument("--formats", default="svg,pdf,png")
    parser.add_argument("--width-mm", type=float, default=183)
    parser.add_argument("--height-mm", type=float, default=105)
    parser.add_argument("--dpi", type=int, default=300)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if (
            args.width_mm <= 0
            or args.height_mm <= 0
            or args.dpi <= 0
            or args.max_rows <= 0
        ):
            raise ValueError(
                f"{CHECK}-OUTPUT-01 dimensions, DPI, and max rows must be positive"
            )
        if not args.effect_scale.strip() or not args.interval_label.strip():
            raise ValueError(
                f"{CHECK}-SEMANTIC-01 effect scale and interval label are required"
            )
        role_columns = [
            args.label_col,
            args.group_col,
            args.estimate_col,
            args.lower_col,
            args.upper_col,
        ]
        if len(role_columns) != len(set(role_columns)):
            raise ValueError(
                f"{CHECK}-SEMANTIC-01 label, group, estimate, lower, and "
                "upper roles must use distinct CSV columns"
            )
        if not args.x_label.strip() or not math.isfinite(args.reference):
            raise ValueError(
                f"{CHECK}-SEMANTIC-01 x label must be nonblank and "
                "reference must be finite"
            )
        formats = parse_formats(args.formats)
        data_manifest = load_data_manifest(
            args.data_manifest,
            [args.input],
            args.run_mode,
            check_id=f"{CHECK}-DEMO-01",
            bundled_demo_paths=[PACK_DIR / "examples" / "demo.csv"],
            semantic_column_bindings={
                "label": args.label_col,
                "group": args.group_col,
                "estimate": args.estimate_col,
                "lower": args.lower_col,
                "upper": args.upper_col,
            },
            numeric_semantic_roles={"estimate", "lower", "upper"},
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
                supported_phases={"confirmatory", "presentation"},
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
            bind_native_semantics(
                figure_contract,
                {
                    "column_roles": {
                        "label": args.label_col,
                        "group": args.group_col,
                        "estimate": args.estimate_col,
                        "lower": args.lower_col,
                        "upper": args.upper_col,
                    },
                    "effect_scale": args.effect_scale,
                    "interval_label": args.interval_label,
                    "reference_value": args.reference,
                    "x_label": args.x_label,
                },
                check_id=f"{CHECK}-CONTRACT-01",
            )
            bind_category_order(
                figure_contract,
                "label",
                data["label_order"],
                check_id=f"{CHECK}-CONTRACT-01",
            )
            bind_category_order(
                figure_contract,
                "group",
                data["group_order"],
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
                    args.output_dir.resolve() / "effect-forest.manifest.json"
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
