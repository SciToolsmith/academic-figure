#!/usr/bin/env python3
"""Render guarded sample-level composition bars from a long CSV table."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from contract import (
    load_data_manifest,
    load_figure_contract,
    parse_formats,
    read_and_validate,
    sha256,
)


IMPLEMENTATION_ID = "composition-bars-v1"
IMPLEMENTATION_VERSION = "1.0.0"


def render(
    args: argparse.Namespace,
    data: dict[str, Any],
    output_dir: Path,
    formats: list[str],
) -> dict[str, Any]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
        from matplotlib.ticker import PercentFormatter
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is required; install the declared implementation dependency"
        ) from exc

    matplotlib.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "axes.unicode_minus": False,
            "svg.fonttype": "none",
            "svg.hashsalt": IMPLEMENTATION_ID,
            "pdf.fonttype": 42,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )

    facets = data["facets"]
    categories = data["categories"]
    width_in = args.width_mm / 25.4
    height_in = args.height_mm / 25.4
    fig, axes_grid = plt.subplots(
        1,
        len(facets),
        figsize=(width_in, height_in),
        dpi=args.dpi,
        sharey=True,
        squeeze=False,
        gridspec_kw={"wspace": 0.08},
    )
    axes = list(axes_grid[0])
    fig.subplots_adjust(left=0.10, right=0.79, bottom=0.19, top=0.77)
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

    for facet_index, (axis, facet) in enumerate(zip(axes, facets)):
        samples = data["samples_by_facet"][facet]
        x_values = list(range(len(samples)))
        bottoms = [0.0] * len(samples)
        for category, color in zip(categories, data["colors"]):
            heights = [
                data["values"][(facet, sample, category)] for sample in samples
            ]
            axis.bar(
                x_values,
                heights,
                width=0.88,
                bottom=bottoms,
                color=color,
                edgecolor="white",
                linewidth=0.35,
            )
            bottoms = [
                bottom + height for bottom, height in zip(bottoms, heights)
            ]
        axis.set_title(facet, fontsize=10.5, fontweight="bold", pad=9)
        axis.set_xlim(-0.55, len(samples) - 0.45)
        axis.set_ylim(0, 1)
        axis.set_axisbelow(True)
        axis.grid(axis="y", color="#E5E8EB", linewidth=0.65)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.spines["bottom"].set_color("#34404A")
        if facet_index == 0:
            axis.spines["left"].set_color("#34404A")
            axis.set_ylabel("Composition", fontsize=10, labelpad=8)
            axis.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
            axis.tick_params(axis="y", labelsize=8.5)
        else:
            axis.spines["left"].set_visible(False)
            axis.tick_params(axis="y", left=False, labelleft=False)
        if data["show_labels"]:
            axis.set_xticks(x_values, samples, rotation=45, ha="right")
            axis.tick_params(axis="x", labelsize=7.5, length=0)
        else:
            axis.set_xticks([])

    handles = [
        Patch(facecolor=color, edgecolor="none", label=category)
        for category, color in zip(categories, data["colors"])
    ]
    legend = fig.legend(
        handles=handles,
        title=args.legend_title,
        loc="upper left",
        bbox_to_anchor=(0.815, 0.77),
        frameon=False,
        fontsize=8.5,
        title_fontsize=9.5,
        labelspacing=0.55,
        borderaxespad=0,
    )
    legend._legend_box.align = "left"

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

    if output_dir.exists():
        if not output_dir.is_dir():
            plt.close(fig)
            raise ValueError(f"output path is not a directory: {output_dir}")
        if any(output_dir.iterdir()):
            plt.close(fig)
            raise ValueError(f"output directory must be empty: {output_dir}")
    else:
        output_dir.mkdir(parents=True)
    targets = [output_dir / f"composition.{fmt}" for fmt in formats]
    targets.extend(
        [
            output_dir / "analysis-table.csv",
            output_dir / "data-validation.json",
        ]
    )
    targets.append(output_dir / "composition.manifest.json")
    existing = [str(path) for path in targets if path.exists()]
    if existing:
        plt.close(fig)
        raise ValueError(
            "refusing to overwrite existing outputs: " + ", ".join(existing)
        )

    artifacts: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix=".composition-stage-", dir=output_dir
    ) as temporary:
        stage_dir = Path(temporary)
        for fmt in formats:
            staged = stage_dir / f"composition.{fmt}"
            metadata: dict[str, Any]
            if fmt == "svg":
                metadata = {
                    "Creator": f"SciPlot {IMPLEMENTATION_ID}",
                    "Date": None,
                }
            elif fmt == "pdf":
                metadata = {
                    "Creator": f"SciPlot {IMPLEMENTATION_ID}",
                    "Title": args.title,
                    "CreationDate": None,
                    "ModDate": None,
                }
            else:
                metadata = {"Software": f"SciPlot {IMPLEMENTATION_ID}"}
            fig.savefig(
                staged,
                format=fmt,
                dpi=args.dpi,
                metadata=metadata,
            )
            artifacts.append(
                {
                    "file": staged.name,
                    "format": fmt,
                    "sha256": sha256(staged),
                    "bytes": staged.stat().st_size,
                }
            )
        plt.close(fig)

        analysis_table = stage_dir / "analysis-table.csv"
        with analysis_table.open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "facet",
                    "sample",
                    "category",
                    "input_value",
                    "denominator",
                    "plotted_fraction",
                ],
            )
            writer.writeheader()
            for facet, sample, category in data["records"]:
                writer.writerow(
                    {
                        "facet": facet,
                        "sample": sample,
                        "category": category,
                        "input_value": f"{data['input_values'][(facet, sample, category)]:.17g}",
                        "denominator": f"{data['denominators'][f'{facet} | {sample}']:.17g}",
                        "plotted_fraction": f"{data['values'][(facet, sample, category)]:.17g}",
                    }
                )
        artifacts.append(
            {
                "file": analysis_table.name,
                "format": "csv",
                "sha256": sha256(analysis_table),
                "bytes": analysis_table.stat().st_size,
            }
        )

        validation = {
            "schema_version": "sciplot.data-validation/v1",
            "status": "PASS",
            "implementation": IMPLEMENTATION_ID,
            "checks": [
                {
                    "id": "CB-INPUT-01",
                    "status": "PASS",
                    "evidence": f"{data['rows']} rows with explicit role bindings",
                },
                {
                    "id": "CB-KEY-01",
                    "status": "PASS",
                    "evidence": "facet-sample-category keys are unique",
                },
                {
                    "id": "CB-GRID-01",
                    "status": "PASS",
                    "evidence": "every sample contains the complete category set",
                },
                {
                    "id": "CB-VALUE-01",
                    "status": "PASS",
                    "evidence": "all values are finite and nonnegative",
                },
                {
                    "id": "CB-DENOM-01",
                    "status": "PASS",
                    "evidence": (
                        "proportion closure validated without normalization"
                        if args.value_mode == "proportion"
                        else "count denominators explicitly converted to fractions"
                    ),
                },
                {
                    "id": "CB-DEMO-01",
                    "status": "PASS",
                    "evidence": f"run mode {args.run_mode} agrees with data manifest",
                },
                *(
                    [
                        {
                            "id": "CB-CONTRACT-01",
                            "status": "PASS",
                            "evidence": (
                                "Figure Contract phase, rows, formats, dimensions, "
                                "and raster DPI agree with the render"
                            ),
                        }
                    ]
                    if data.get("figure_contract")
                    else []
                ),
            ],
            "rows_read": data["rows"],
            "rows_included": data["rows"],
            "exclusions": [],
            "input_sha256": sha256(data["path"]),
            "data_manifest_sha256": data["data_manifest"]["_sha256"],
        }
        validation_path = stage_dir / "data-validation.json"
        validation_path.write_text(
            json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        artifacts.append(
            {
                "file": validation_path.name,
                "format": "json",
                "sha256": sha256(validation_path),
                "bytes": validation_path.stat().st_size,
            }
        )

        manifest = {
            "schema_version": "sciplot.render-manifest/v1",
            "figure_contract": (
                {
                    "file": data["figure_contract"]["_path"],
                    "sha256": data["figure_contract"]["_sha256"],
                    "phase": data["figure_contract"]["task"]["phase"],
                    "formats": data["figure_contract"]["target"]["formats"],
                    "lint": data["figure_contract"].get("_contract_lint"),
                }
                if data.get("figure_contract")
                else None
            ),
            "implementation": {
                "id": IMPLEMENTATION_ID,
                "version": IMPLEMENTATION_VERSION,
                "source_sha256": sha256(Path(__file__).resolve()),
                "source_files_sha256": {
                    "render.py": sha256(Path(__file__).resolve()),
                    "contract.py": sha256(
                        Path(__file__).resolve().with_name("contract.py")
                    ),
                },
            },
            "data": {
                "run_mode": args.run_mode,
                "synthetic": data["data_manifest"]["synthetic"],
                "production_use_allowed": data["data_manifest"][
                    "production_use_allowed"
                ],
                "input_file": str(data["path"]),
                "input_sha256": sha256(data["path"]),
                "data_manifest_file": data["data_manifest"]["_path"],
                "data_manifest_sha256": data["data_manifest"]["_sha256"],
                "rows_read": data["rows"],
                "rows_included": data["rows"],
                "exclusions": [],
                "field_mapping": data["roles"],
                "analysis_unit": "facet plus sample",
                "replicate_unit": "sample",
                "facet_order": data["facets"],
                "category_order": data["categories"],
                "value_mode": args.value_mode,
                "transformation": (
                    "counts divided by the explicit per-sample denominator"
                    if args.value_mode == "counts"
                    else "none"
                ),
                "denominators": data["denominators"],
                "sum_tolerance": args.sum_tolerance,
            },
            "figure": {
                "width_mm": args.width_mm,
                "height_mm": args.height_mm,
                "dpi_for_raster": args.dpi,
                "sample_labels": (
                    "shown" if data["show_labels"] else "hidden"
                ),
                "colors_by_category": dict(
                    zip(data["categories"], data["colors"])
                ),
                "tight_crop": False,
            },
            "scientific_scope": {
                "descriptive_only": True,
                "inferential_statistics_computed": False,
                "uncertainty_computed": False,
            },
            "environment": {
                "python": sys.version.split()[0],
                "matplotlib": matplotlib.__version__,
            },
            "artifacts": artifacts,
            "warnings": data["warnings"],
        }
        staged_manifest = stage_dir / "composition.manifest.json"
        staged_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        for staged in [
            *(stage_dir / item["file"] for item in artifacts),
            staged_manifest,
        ]:
            os.replace(staged, output_dir / staged.name)

    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Render sample-level composition bars with explicit denominator "
            "and smoke/production guards."
        )
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--data-manifest", type=Path, required=True)
    parser.add_argument(
        "--figure-contract",
        type=Path,
        help="Required in production; binds semantics and output arguments.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--run-mode", choices=("production", "smoke"), required=True
    )
    parser.add_argument(
        "--value-mode", choices=("proportion", "counts"), required=True
    )
    parser.add_argument("--sample-col", default="sample")
    parser.add_argument("--facet-col", default="facet")
    parser.add_argument("--category-col", default="category")
    parser.add_argument("--value-col", default="value")
    parser.add_argument("--facet-order")
    parser.add_argument("--category-order")
    parser.add_argument("--colors")
    parser.add_argument("--sum-tolerance", type=float, default=1e-6)
    parser.add_argument(
        "--sample-labels", choices=("auto", "show", "hide"), default="auto"
    )
    parser.add_argument("--title", default="Composition by sample")
    parser.add_argument("--subtitle", default="")
    parser.add_argument("--legend-title", default="Category")
    parser.add_argument("--formats", default="svg,pdf,png")
    parser.add_argument("--width-mm", type=float, default=183.0)
    parser.add_argument("--height-mm", type=float, default=105.0)
    parser.add_argument("--dpi", type=int, default=300)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.width_mm <= 0 or args.height_mm <= 0:
            raise ValueError("physical dimensions must be positive")
        if args.dpi < 72:
            raise ValueError("--dpi must be at least 72")
        formats = parse_formats(args.formats)
        input_path = args.input.resolve()
        if not input_path.is_file():
            raise ValueError(f"CB-INPUT-01 input file not found: {input_path}")
        data_manifest = load_data_manifest(
            args.data_manifest,
            input_path,
            args.run_mode,
            bundled_demo_path=(
                Path(__file__).resolve().parent / "examples" / "demo.csv"
            ),
            semantic_column_bindings={
                "sample": args.sample_col,
                "facet": args.facet_col,
                "category": args.category_col,
                "value": args.value_col,
            },
            numeric_semantic_roles=["value"],
        )
        data = read_and_validate(args, data_manifest)
        if args.run_mode == "production" and args.figure_contract is None:
            raise ValueError(
                "CB-CONTRACT-01 production mode requires --figure-contract"
            )
        figure_contract = (
            load_figure_contract(
                args.figure_contract,
                run_mode=args.run_mode,
                value_mode=args.value_mode,
                formats=formats,
                width_mm=args.width_mm,
                height_mm=args.height_mm,
                dpi=args.dpi,
                rows=data["rows"],
                implementation_id=IMPLEMENTATION_ID,
                implementation_version=IMPLEMENTATION_VERSION,
            )
            if args.figure_contract is not None
            else None
        )
        data["figure_contract"] = figure_contract
        manifest = render(args, data, args.output_dir.resolve(), formats)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"render failed: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "status": "rendered",
                "implementation": IMPLEMENTATION_ID,
                "run_mode": args.run_mode,
                "output_dir": str(args.output_dir.resolve()),
                "artifacts": [
                    item["file"] for item in manifest["artifacts"]
                ],
                "manifest": "composition.manifest.json",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
