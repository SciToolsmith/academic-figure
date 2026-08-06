"""Regression tests for SciPlot-native runnable implementations."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_implementations.py"
PACK = ROOT / "implementations" / "python" / "composition-bars-v1"
RENDERER = PACK / "render.py"
DEMO = PACK / "examples" / "demo.csv"
INSPECTOR = ROOT / "scripts" / "inspect_artifacts.py"
DELIVERY_VALIDATOR = ROOT / "scripts" / "validate_delivery.py"


def run(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


class ImplementationCatalogTests(unittest.TestCase):
    def test_index_and_source_hash_validate(self) -> None:
        completed = run(str(VALIDATOR), "--pretty")
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["count"], 1)
        self.assertEqual(
            result["implementations"][0]["id"], "composition-bars-v1"
        )
        self.assertEqual(
            result["implementations"][0]["supported_task_phases"],
            ["descriptive", "presentation"],
        )

    def test_renderer_does_not_use_silent_tight_crop(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (RENDERER, PACK / "contract.py")
        )
        self.assertNotIn("bbox_inches", source)
        self.assertIn('"svg.fonttype": "none"', source)
        for case_specific in ("Microbe_", "Day 0", "seed 123", "case-packs"):
            self.assertNotIn(case_specific, source)


@unittest.skipUnless(
    importlib.util.find_spec("matplotlib") is not None,
    "matplotlib is an optional runtime dependency",
)
class CompositionRendererRuntimeTests(unittest.TestCase):
    def write_smoke_input(
        self, directory: Path, name: str, csv_text: str
    ) -> tuple[Path, Path]:
        import hashlib

        input_path = directory / f"{name}.csv"
        input_path.write_text(csv_text, encoding="utf-8")
        manifest_path = directory / f"{name}.manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "synthetic": True,
                    "production_use_allowed": False,
                    "input_sha256": hashlib.sha256(
                        input_path.read_bytes()
                    ).hexdigest(),
                }
            ),
            encoding="utf-8",
        )
        return input_path, manifest_path

    def write_production_input(
        self,
        directory: Path,
    ) -> tuple[Path, Path]:
        input_path = directory / "production.csv"
        input_path.write_text(
            "facet,sample,category,value\n"
            "F1,S1,A,1\n"
            "F1,S1,B,3\n"
            "F1,S2,A,6\n"
            "F1,S2,B,2\n",
            encoding="utf-8",
        )
        manifest_path = directory / "production.manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "synthetic": False,
                    "production_use_allowed": True,
                    "input_sha256": hashlib.sha256(
                        input_path.read_bytes()
                    ).hexdigest(),
                }
            ),
            encoding="utf-8",
        )
        return input_path, manifest_path

    def write_figure_contract(
        self,
        directory: Path,
        *,
        formats: list[str] | None = None,
        phase: str = "descriptive",
    ) -> Path:
        contract_path = directory / (
            "figure-contract-" + "-".join(formats or ["svg"]) + ".json"
        )
        contract_path.write_text(
            json.dumps(
                {
                    "contract_version": 1,
                    "task": {
                        "phase": phase,
                        "profile": "minimal",
                        "execution_state": "proceed",
                    },
                    "target": {
                        "width_mm": 183,
                        "height_mm": 105,
                        "formats": formats or ["svg"],
                        "primary_format": "svg",
                        "preview_format": "svg",
                        "resolution_dpi": (
                            300
                            if {"png", "tiff"} & set(formats or ["svg"])
                            else None
                        ),
                    },
                    "data_integrity": {
                        "included_rows_or_items": 4,
                        "transformations": [
                            {
                                "operation": "divide counts by each sample total",
                                "guard": "positive denominator",
                            }
                        ],
                    },
                    "implementation": {
                        "native_implementation": {
                            "id": "composition-bars-v1",
                            "version": "1.0.0",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        return contract_path

    def render_demo(
        self, output_dir: Path, *extra: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        return run(
            str(RENDERER),
            "--input",
            str(DEMO),
            "--data-manifest",
            str(PACK / "examples" / "demo-data.json"),
            "--output-dir",
            str(output_dir),
            "--run-mode",
            "smoke",
            "--value-mode",
            "proportion",
            "--formats",
            "svg",
            "--facet-order",
            "Day 0,Day 7",
            "--category-order",
            "Alpha,Beta,Gamma,Other",
            *extra,
            check=check,
        )

    def test_demo_render_is_watermarked_and_has_auditable_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp) / "out"
            completed = self.render_demo(output_dir)
            result = json.loads(completed.stdout)
            manifest = json.loads(
                (output_dir / "composition.manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(result["status"], "rendered")
            self.assertEqual(manifest["data"]["run_mode"], "smoke")
            self.assertFalse(manifest["data"]["production_use_allowed"])
            self.assertEqual(manifest["data"]["rows_read"], 24)
            self.assertEqual(manifest["data"]["rows_included"], 24)
            self.assertEqual(manifest["data"]["exclusions"], [])
            self.assertFalse(manifest["figure"]["tight_crop"])
            with (output_dir / "analysis-table.csv").open(
                "r", encoding="utf-8", newline=""
            ) as handle:
                import csv

                analysis_rows = list(csv.DictReader(handle))
            self.assertEqual(len(analysis_rows), 24)
            validation = json.loads(
                (output_dir / "data-validation.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(validation["status"], "PASS")
            svg = (output_dir / "composition.svg").read_text(encoding="utf-8")
            self.assertIn("SYNTHETIC SMOKE TEST", svg)

            inspected = run(
                str(INSPECTOR),
                str(output_dir / "composition.svg"),
                "--width-mm",
                "183",
                "--height-mm",
                "105",
                "--require-svg-text",
            )
            report = json.loads(inspected.stdout)
            self.assertEqual(report["status"], "PASS")

    def test_simulated_input_cannot_be_declared_production(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            completed = run(
                str(RENDERER),
                "--input",
                str(DEMO),
                "--data-manifest",
                str(PACK / "examples" / "demo-data.json"),
                "--output-dir",
                str(Path(temp) / "out"),
                "--run-mode",
                "production",
                "--value-mode",
                "proportion",
                "--formats",
                "svg",
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("CB-DEMO-01", completed.stderr)

    def test_production_requires_a_figure_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            input_path, manifest_path = self.write_production_input(base)
            completed = run(
                str(RENDERER),
                "--input",
                str(input_path),
                "--data-manifest",
                str(manifest_path),
                "--output-dir",
                str(base / "out"),
                "--run-mode",
                "production",
                "--value-mode",
                "counts",
                "--formats",
                "svg",
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("CB-CONTRACT-01", completed.stderr)

    def test_production_contract_binds_formats_phase_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            input_path, manifest_path = self.write_production_input(base)
            contract_path = self.write_figure_contract(base)
            completed = run(
                str(RENDERER),
                "--input",
                str(input_path),
                "--data-manifest",
                str(manifest_path),
                "--figure-contract",
                str(contract_path),
                "--output-dir",
                str(base / "out"),
                "--run-mode",
                "production",
                "--value-mode",
                "counts",
                "--formats",
                "svg",
            )
            self.assertEqual(
                json.loads(completed.stdout)["status"],
                "rendered",
            )
            manifest = json.loads(
                (base / "out" / "composition.manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                manifest["figure_contract"]["sha256"],
                hashlib.sha256(contract_path.read_bytes()).hexdigest(),
            )
            delivery = run(
                str(DELIVERY_VALIDATOR),
                "--contract",
                str(contract_path),
                "--manifest",
                str(base / "out" / "composition.manifest.json"),
                "--artifact-dir",
                str(base / "out"),
            )
            self.assertEqual(json.loads(delivery.stdout)["status"], "PASS")

            mismatched = self.write_figure_contract(
                base,
                formats=["svg", "png"],
            )
            rejected = run(
                str(RENDERER),
                "--input",
                str(input_path),
                "--data-manifest",
                str(manifest_path),
                "--figure-contract",
                str(mismatched),
                "--output-dir",
                str(base / "mismatch"),
                "--run-mode",
                "production",
                "--value-mode",
                "counts",
                "--formats",
                "svg",
                check=False,
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("CLI formats do not match", rejected.stderr)

    def test_proportion_closure_failure_is_not_silently_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            input_path, manifest_path = self.write_smoke_input(
                Path(temp),
                "invalid",
                "source_type,facet,sample,category,value\n"
                "simulated,F1,S1,A,0.2\n"
                "simulated,F1,S1,B,0.2\n",
            )
            completed = run(
                str(RENDERER),
                "--input",
                str(input_path),
                "--data-manifest",
                str(manifest_path),
                "--output-dir",
                str(Path(temp) / "out"),
                "--run-mode",
                "smoke",
                "--value-mode",
                "proportion",
                "--formats",
                "svg",
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("CB-DENOM-01", completed.stderr)

    def test_count_mode_records_each_denominator_and_plotted_fraction(self) -> None:
        import csv

        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            input_path, manifest_path = self.write_smoke_input(
                base,
                "counts",
                "source_type,facet,sample,category,value\n"
                "simulated,F1,S1,A,1\n"
                "simulated,F1,S1,B,3\n"
                "simulated,F1,S2,A,6\n"
                "simulated,F1,S2,B,2\n",
            )
            output_dir = base / "out"
            completed = run(
                str(RENDERER),
                "--input",
                str(input_path),
                "--data-manifest",
                str(manifest_path),
                "--output-dir",
                str(output_dir),
                "--run-mode",
                "smoke",
                "--value-mode",
                "counts",
                "--formats",
                "svg",
            )
            self.assertEqual(json.loads(completed.stdout)["status"], "rendered")
            with (output_dir / "analysis-table.csv").open(
                "r", encoding="utf-8", newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(
                [float(row["denominator"]) for row in rows],
                [4.0, 4.0, 8.0, 8.0],
            )
            self.assertEqual(
                [float(row["plotted_fraction"]) for row in rows],
                [0.25, 0.75, 0.75, 0.25],
            )

    def test_duplicate_missing_and_invalid_values_fail_closed(self) -> None:
        cases = {
            "duplicate": (
                "source_type,facet,sample,category,value\n"
                "simulated,F1,S1,A,0.5\n"
                "simulated,F1,S1,A,0.5\n",
                "CB-KEY-01",
            ),
            "missing-category": (
                "source_type,facet,sample,category,value\n"
                "simulated,F1,S1,A,0.5\n"
                "simulated,F1,S1,B,0.5\n"
                "simulated,F1,S2,A,1.0\n",
                "CB-GRID-01",
            ),
            "nonfinite": (
                "source_type,facet,sample,category,value\n"
                "simulated,F1,S1,A,NaN\n"
                "simulated,F1,S1,B,0.5\n",
                "CB-VALUE-01",
            ),
            "negative": (
                "source_type,facet,sample,category,value\n"
                "simulated,F1,S1,A,-0.2\n"
                "simulated,F1,S1,B,1.2\n",
                "CB-VALUE-01",
            ),
        }
        for name, (csv_text, expected) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                base = Path(temp)
                input_path, manifest_path = self.write_smoke_input(
                    base, name, csv_text
                )
                completed = run(
                    str(RENDERER),
                    "--input",
                    str(input_path),
                    "--data-manifest",
                    str(manifest_path),
                    "--output-dir",
                    str(base / "out"),
                    "--run-mode",
                    "smoke",
                    "--value-mode",
                    "proportion",
                    "--formats",
                    "svg",
                    check=False,
                )
                self.assertEqual(completed.returncode, 2)
                self.assertIn(expected, completed.stderr)

    def test_renderer_refuses_to_overwrite_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp) / "out"
            self.render_demo(output_dir)
            completed = self.render_demo(output_dir, check=False)
            self.assertEqual(completed.returncode, 2)
            self.assertIn("output directory must be empty", completed.stderr)


if __name__ == "__main__":
    unittest.main()
