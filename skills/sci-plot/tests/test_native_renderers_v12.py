"""Regression tests for SciPlot v1.2 native Python renderers."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON_IMPLEMENTATIONS = ROOT / "implementations" / "python"
PACKS = {
    "raw": PYTHON_IMPLEMENTATIONS / "raw-distribution-v1",
    "paired": PYTHON_IMPLEMENTATIONS / "paired-change-v1",
    "forest": PYTHON_IMPLEMENTATIONS / "effect-forest-v1",
}


def run(
    renderer: Path,
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(renderer), *arguments],
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


def write_fixture(
    directory: Path,
    name: str,
    csv_text: str,
) -> tuple[Path, Path]:
    input_path = directory / f"{name}.csv"
    input_path.write_text(csv_text, encoding="utf-8")
    manifest_path = directory / f"{name}.data.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "sciplot.data-manifest/v1",
                "synthetic": True,
                "production_use_allowed": False,
                "inputs": {
                    input_path.name: hashlib.sha256(
                        input_path.read_bytes()
                    ).hexdigest()
                },
            }
        ),
        encoding="utf-8",
    )
    return input_path, manifest_path


@unittest.skipUnless(
    importlib.util.find_spec("matplotlib") is not None,
    "matplotlib is an optional runtime dependency",
)
class NativeRendererV12Tests(unittest.TestCase):
    def smoke_arguments(
        self,
        kind: str,
        output_dir: Path,
    ) -> list[str]:
        pack = PACKS[kind]
        common = [
            "--input",
            str(pack / "examples" / "demo.csv"),
            "--data-manifest",
            str(pack / "examples" / "demo-data.json"),
            "--output-dir",
            str(output_dir),
            "--run-mode",
            "smoke",
            "--formats",
            "svg",
        ]
        if kind == "raw":
            return [
                *common,
                "--group-order",
                "Control,Treatment 1,Treatment 2",
            ]
        if kind == "paired":
            return [
                *common,
                "--group-order",
                "Control,Treatment",
                "--timepoint-order",
                "Baseline,Week 8",
            ]
        return [
            *common,
            "--label-order",
            (
                "All participants,Age 65 or younger,Older than 65,"
                "Female,Male,High baseline score"
            ),
            "--group-order",
            "Overall,Age,Sex,Baseline score",
            "--effect-scale",
            "adjusted mean difference",
            "--interval-label",
            "95% confidence interval",
        ]

    def test_all_three_demo_renderers_emit_auditable_svg_bundles(self) -> None:
        expected = {
            "raw": ("distribution", 18),
            "paired": ("paired-change", 24),
            "forest": ("effect-forest", 6),
        }
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for kind, (basename, rows) in expected.items():
                with self.subTest(kind=kind):
                    output_dir = base / kind
                    completed = run(
                        PACKS[kind] / "render.py",
                        *self.smoke_arguments(kind, output_dir),
                    )
                    result = json.loads(completed.stdout)
                    self.assertEqual(result["status"], "rendered")
                    manifest = json.loads(
                        (output_dir / f"{basename}.manifest.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    self.assertEqual(manifest["data"]["rows_read"], rows)
                    self.assertEqual(manifest["data"]["rows_included"], rows)
                    self.assertTrue(manifest["figure"]["watermark"])
                    self.assertFalse(manifest["figure"]["tight_crop"])
                    self.assertIn(
                        "SYNTHETIC SMOKE TEST",
                        (output_dir / f"{basename}.svg").read_text(
                            encoding="utf-8"
                        ),
                    )
                    validation = json.loads(
                        (output_dir / "data-validation.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    self.assertEqual(validation["status"], "PASS")
                    self.assertTrue(
                        all(
                            check["status"] == "PASS"
                            and check.get("evidence")
                            for check in validation["checks"]
                        )
                    )
                    with (output_dir / "analysis-table.csv").open(
                        "r",
                        encoding="utf-8",
                        newline="",
                    ) as handle:
                        analysis_rows = list(csv.DictReader(handle))
                    self.assertTrue(analysis_rows)

    def test_raw_distribution_rejects_duplicate_observation_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            input_path, manifest = write_fixture(
                base,
                "duplicate",
                "source_type,observation_id,group,value\n"
                "simulated,A,G1,1\n"
                "simulated,A,G1,2\n",
            )
            completed = run(
                PACKS["raw"] / "render.py",
                "--input",
                str(input_path),
                "--data-manifest",
                str(manifest),
                "--output-dir",
                str(base / "out"),
                "--run-mode",
                "smoke",
                "--formats",
                "svg",
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("RD-KEY-01", completed.stderr)

    def test_raw_distribution_rejects_nonfinite_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            input_path, manifest = write_fixture(
                base,
                "nonfinite",
                "source_type,observation_id,group,value\n"
                "simulated,A,G1,1\n"
                "simulated,B,G1,nan\n",
            )
            completed = run(
                PACKS["raw"] / "render.py",
                "--input",
                str(input_path),
                "--data-manifest",
                str(manifest),
                "--output-dir",
                str(base / "out"),
                "--run-mode",
                "smoke",
                "--formats",
                "svg",
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("RD-VALUE-01", completed.stderr)

    def test_paired_change_rejects_incomplete_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            input_path, manifest = write_fixture(
                base,
                "incomplete",
                "source_type,subject,group,timepoint,value\n"
                "simulated,S1,G1,T0,1\n"
                "simulated,S1,G1,T1,2\n"
                "simulated,S2,G1,T0,3\n",
            )
            completed = run(
                PACKS["paired"] / "render.py",
                "--input",
                str(input_path),
                "--data-manifest",
                str(manifest),
                "--output-dir",
                str(base / "out"),
                "--run-mode",
                "smoke",
                "--timepoint-order",
                "T0,T1",
                "--formats",
                "svg",
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("PC-PAIR-01", completed.stderr)

    def test_paired_change_rejects_group_drift_within_subject(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            input_path, manifest = write_fixture(
                base,
                "group-drift",
                "source_type,subject,group,timepoint,value\n"
                "simulated,S1,G1,T0,1\n"
                "simulated,S1,G2,T1,2\n",
            )
            completed = run(
                PACKS["paired"] / "render.py",
                "--input",
                str(input_path),
                "--data-manifest",
                str(manifest),
                "--output-dir",
                str(base / "out"),
                "--run-mode",
                "smoke",
                "--timepoint-order",
                "T0,T1",
                "--formats",
                "svg",
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("PC-GROUP-01", completed.stderr)

    def test_effect_forest_rejects_interval_not_containing_estimate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            input_path, manifest = write_fixture(
                base,
                "invalid-interval",
                "source_type,label,group,estimate,lower,upper\n"
                "simulated,Effect A,G1,0.5,0.6,0.8\n",
            )
            completed = run(
                PACKS["forest"] / "render.py",
                "--input",
                str(input_path),
                "--data-manifest",
                str(manifest),
                "--output-dir",
                str(base / "out"),
                "--run-mode",
                "smoke",
                "--effect-scale",
                "difference",
                "--interval-label",
                "95% confidence interval",
                "--formats",
                "svg",
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("EF-INTERVAL-01", completed.stderr)

    def test_effect_forest_rejects_duplicate_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            input_path, manifest = write_fixture(
                base,
                "duplicate-label",
                "source_type,label,group,estimate,lower,upper\n"
                "simulated,Effect A,G1,0.5,0.2,0.8\n"
                "simulated,Effect A,G1,0.4,0.1,0.7\n",
            )
            completed = run(
                PACKS["forest"] / "render.py",
                "--input",
                str(input_path),
                "--data-manifest",
                str(manifest),
                "--output-dir",
                str(base / "out"),
                "--run-mode",
                "smoke",
                "--effect-scale",
                "difference",
                "--interval-label",
                "95% confidence interval",
                "--formats",
                "svg",
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("EF-KEY-01", completed.stderr)

    def test_production_rejects_bundled_demo_even_with_forged_manifest(self) -> None:
        contract_by_kind = {
            "raw": "figure-contract.descriptive-distribution.example.json",
            "paired": "figure-contract.descriptive-paired.example.json",
            "forest": "figure-contract.presentation-forest.example.json",
        }
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for kind, contract_name in contract_by_kind.items():
                pack = PACKS[kind]
                demo = pack / "examples" / "demo.csv"
                copied_demo = base / f"{kind}-copied-demo.csv"
                copied_demo.write_bytes(demo.read_bytes())
                modified_demo = base / f"{kind}-modified-demo.csv"
                modified_demo.write_text(
                    demo.read_text(encoding="utf-8") + "\n",
                    encoding="utf-8",
                )
                explicit_synthetic = base / f"{kind}-synthetic-marker.csv"
                explicit_synthetic.write_text(
                    demo.read_text(encoding="utf-8").replace(
                        "simulated,",
                        "synthetic,",
                    ),
                    encoding="utf-8",
                )
                provenance_only_copy = (
                    base / f"{kind}-provenance-only-copy.csv"
                )
                provenance_only_copy.write_text(
                    demo.read_text(encoding="utf-8").replace(
                        "simulated,",
                        "observed,",
                    ),
                    encoding="utf-8",
                )
                numeric_tokens = {
                    "raw": ("Control,4.2", "Control,4.20"),
                    "paired": ("Baseline,5.0", "Baseline,5.00"),
                    "forest": (",0.42,0.18", ",0.420,0.18"),
                }
                before, after = numeric_tokens[kind]
                numeric_format_copy = (
                    base / f"{kind}-numeric-format-copy.csv"
                )
                numeric_format_copy.write_text(
                    demo.read_text(encoding="utf-8")
                    .replace("simulated,", "observed,")
                    .replace(before, after, 1),
                    encoding="utf-8",
                )
                renamed_role_copy = base / f"{kind}-renamed-role-copy.csv"
                role_renames = {
                    "raw": ("value", "measurement", "--value-col"),
                    "paired": ("value", "measurement", "--value-col"),
                    "forest": (
                        "estimate",
                        "point_estimate",
                        "--estimate-col",
                    ),
                }
                old_role, new_role, role_flag = role_renames[kind]
                renamed_role_copy.write_text(
                    demo.read_text(encoding="utf-8")
                    .replace("simulated,", "observed,")
                    .replace(old_role, new_role, 1),
                    encoding="utf-8",
                )
                for variant, candidate, variant_arguments in (
                    ("bundled-path", demo, []),
                    ("byte-identical-copy", copied_demo, []),
                    ("modified-simulated-copy", modified_demo, []),
                    ("explicit-synthetic-marker", explicit_synthetic, []),
                    ("provenance-only-copy", provenance_only_copy, []),
                    ("numeric-format-copy", numeric_format_copy, []),
                    (
                        "renamed-scientific-role-copy",
                        renamed_role_copy,
                        [role_flag, new_role],
                    ),
                ):
                    forged_manifest = (
                        base / f"{kind}-{variant}-production.json"
                    )
                    forged_manifest.write_text(
                        json.dumps(
                            {
                                "schema_version": "sciplot.data-manifest/v1",
                                "synthetic": False,
                                "production_use_allowed": True,
                                "inputs": {
                                    candidate.name: hashlib.sha256(
                                        candidate.read_bytes()
                                    ).hexdigest()
                                },
                            }
                        ),
                        encoding="utf-8",
                    )
                    arguments = [
                        "--input",
                        str(candidate),
                        "--data-manifest",
                        str(forged_manifest),
                        "--figure-contract",
                        str(ROOT / "references" / contract_name),
                        "--output-dir",
                        str(base / f"{kind}-{variant}-out"),
                        "--run-mode",
                        "production",
                        "--formats",
                        "svg,pdf,png",
                        *variant_arguments,
                    ]
                    if kind == "raw":
                        arguments.extend(
                            [
                                "--group-order",
                                "Control,Treatment 1,Treatment 2",
                            ]
                        )
                    elif kind == "paired":
                        arguments.extend(
                            [
                                "--group-order",
                                "Control,Treatment",
                                "--timepoint-order",
                                "Baseline,Week 8",
                            ]
                        )
                    else:
                        arguments.extend(
                            [
                                "--label-order",
                                (
                                    "All participants,Age 65 or younger,"
                                    "Older than 65,Female,Male,"
                                    "High baseline score"
                                ),
                                "--group-order",
                                "Overall,Age,Sex,Baseline score",
                                "--effect-scale",
                                "adjusted mean difference",
                                "--interval-label",
                                "95% confidence interval",
                            ]
                        )
                    with self.subTest(kind=kind, variant=variant):
                        completed = run(
                            pack / "render.py",
                            *arguments,
                            check=False,
                        )
                        self.assertEqual(completed.returncode, 2)
                        self.assertIn("-DEMO-01", completed.stderr)

    def test_effect_forest_rejects_reused_column_roles(self) -> None:
        pack = PACKS["forest"]
        with tempfile.TemporaryDirectory() as temporary:
            for label, mutation in (
                (
                    "numeric roles",
                    ["--estimate-col", "lower", "--lower-col", "lower"],
                ),
                (
                    "label/group roles",
                    ["--label-col", "group", "--group-col", "group"],
                ),
            ):
                with self.subTest(label=label):
                    completed = run(
                        pack / "render.py",
                        *self.smoke_arguments(
                            "forest",
                            Path(temporary) / label.replace("/", "-"),
                        ),
                        *mutation,
                        check=False,
                    )
                    self.assertEqual(completed.returncode, 2)
                    self.assertIn("EF-SEMANTIC-01", completed.stderr)
                    self.assertIn("distinct CSV columns", completed.stderr)

    def test_effect_forest_contract_binds_scientific_semantics(self) -> None:
        pack = PACKS["forest"]
        demo_rows = list(
            csv.DictReader(
                (pack / "examples" / "demo.csv").read_text(
                    encoding="utf-8"
                ).splitlines()
            )
        )
        fieldnames = [
            "source_type",
            "label",
            "group",
            "estimate",
            "estimate_alias",
            "lower",
            "upper",
        ]
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            input_path = base / "forest-production.csv"
            production_intervals = (
                ("0.31", "0.08", "0.54"),
                ("0.47", "0.15", "0.79"),
                ("0.28", "-0.06", "0.62"),
                ("0.39", "0.05", "0.73"),
                ("0.24", "-0.04", "0.52"),
                ("0.61", "0.23", "0.99"),
            )
            with input_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                for row, interval in zip(demo_rows, production_intervals):
                    row["source_type"] = "observed"
                    row["estimate"], row["lower"], row["upper"] = interval
                    row["estimate_alias"] = row["estimate"]
                    writer.writerow(row)
            manifest_path = base / "forest-production.data.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": "sciplot.data-manifest/v1",
                        "synthetic": False,
                        "production_use_allowed": True,
                        "inputs": {
                            input_path.name: hashlib.sha256(
                                input_path.read_bytes()
                            ).hexdigest()
                        },
                    }
                ),
                encoding="utf-8",
            )
            common = [
                "--input",
                str(input_path),
                "--data-manifest",
                str(manifest_path),
                "--figure-contract",
                str(
                    ROOT
                    / "references"
                    / "figure-contract.presentation-forest.example.json"
                ),
                "--run-mode",
                "production",
                "--formats",
                "svg,pdf,png",
                "--label-order",
                (
                    "All participants,Age 65 or younger,Older than 65,"
                    "Female,Male,High baseline score"
                ),
                "--group-order",
                "Overall,Age,Sex,Baseline score",
                "--effect-scale",
                "adjusted mean difference",
                "--interval-label",
                "95% confidence interval",
                "--x-label",
                "Adjusted mean difference (declared units)",
            ]
            valid_output = base / "out-valid"
            completed = run(
                pack / "render.py",
                *common,
                "--output-dir",
                str(valid_output),
            )
            self.assertEqual(json.loads(completed.stdout)["status"], "rendered")
            manifest = json.loads(
                (valid_output / "effect-forest.manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                manifest["figure_contract"]["lint"]["status"],
                "PASS",
            )
            mutations = {
                "estimate column": ["--estimate-col", "estimate_alias"],
                "effect scale": ["--effect-scale", "odds ratio"],
                "interval label": [
                    "--interval-label",
                    "99% confidence interval",
                ],
                "reference": ["--reference", "123"],
                "x label": ["--x-label", "Undeclared axis"],
            }
            for label, mutation in mutations.items():
                with self.subTest(label=label):
                    completed = run(
                        pack / "render.py",
                        *common,
                        *mutation,
                        "--output-dir",
                        str(base / f"out-{label.replace(' ', '-')}"),
                        check=False,
                    )
                    self.assertEqual(completed.returncode, 2)
                    self.assertIn("EF-CONTRACT-01", completed.stderr)

    def test_production_requires_canonical_final_contract_pass(self) -> None:
        pack = PACKS["raw"]
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            input_path = base / "observed.csv"
            input_path.write_text(
                (pack / "examples" / "demo.csv")
                .read_text(encoding="utf-8")
                .replace(
                    "simulated,A01,Control,4.2",
                    "observed,A01,Control,4.25",
                    1,
                )
                .replace("simulated,", "observed,"),
                encoding="utf-8",
            )
            manifest_path = base / "observed.data.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": "sciplot.data-manifest/v1",
                        "synthetic": False,
                        "production_use_allowed": True,
                        "inputs": {
                            input_path.name: hashlib.sha256(
                                input_path.read_bytes()
                            ).hexdigest()
                        },
                    }
                ),
                encoding="utf-8",
            )
            contract = json.loads(
                (
                    ROOT
                    / "references"
                    / "figure-contract.descriptive-distribution.example.json"
                ).read_text(encoding="utf-8")
            )
            contract["acceptance"] = []
            contract_path = base / "invalid-final-contract.json"
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            output_dir = base / "out"

            completed = run(
                pack / "render.py",
                "--input",
                str(input_path),
                "--data-manifest",
                str(manifest_path),
                "--figure-contract",
                str(contract_path),
                "--output-dir",
                str(output_dir),
                "--run-mode",
                "production",
                "--group-order",
                "Control,Treatment 1,Treatment 2",
                "--formats",
                "svg,pdf,png",
                check=False,
            )

            self.assertEqual(completed.returncode, 2)
            self.assertIn("SCIPLOT-CONTRACT-FINAL", completed.stderr)
            self.assertIn("CT-042", completed.stderr)
            self.assertFalse(output_dir.exists())

    def test_contract_order_cannot_silently_disagree_with_renderer(self) -> None:
        pack = PACKS["raw"]
        with tempfile.TemporaryDirectory() as temporary:
            completed = run(
                pack / "render.py",
                "--input",
                str(pack / "examples" / "demo.csv"),
                "--data-manifest",
                str(pack / "examples" / "demo-data.json"),
                "--figure-contract",
                str(
                    ROOT
                    / "references"
                    / "figure-contract.descriptive-distribution.example.json"
                ),
                "--output-dir",
                str(Path(temporary) / "out"),
                "--run-mode",
                "smoke",
                "--group-order",
                "Treatment 2,Treatment 1,Control",
                "--formats",
                "svg,pdf,png",
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("RD-CONTRACT-01", completed.stderr)
            self.assertIn("category_order.group", completed.stderr)

    def test_contract_native_version_must_match_renderer(self) -> None:
        pack = PACKS["paired"]
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            contract = json.loads(
                (
                    ROOT
                    / "references"
                    / "figure-contract.descriptive-paired.example.json"
                ).read_text(encoding="utf-8")
            )
            contract["implementation"]["native_implementation"][
                "version"
            ] = "9.9.9"
            contract_path = base / "wrong-version.json"
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            completed = run(
                pack / "render.py",
                "--input",
                str(pack / "examples" / "demo.csv"),
                "--data-manifest",
                str(pack / "examples" / "demo-data.json"),
                "--figure-contract",
                str(contract_path),
                "--output-dir",
                str(base / "out"),
                "--run-mode",
                "smoke",
                "--group-order",
                "Control,Treatment",
                "--timepoint-order",
                "Baseline,Week 8",
                "--formats",
                "svg,pdf,png",
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("PC-CONTRACT-01", completed.stderr)
            self.assertIn("version does not match", completed.stderr)

    def test_new_renderers_have_editable_svg_and_no_tight_crop(self) -> None:
        shared = (
            PYTHON_IMPLEMENTATIONS / "_shared" / "runtime.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"svg.fonttype": "none"', shared)
        self.assertNotIn("bbox_inches", shared)
        for pack in PACKS.values():
            source = (pack / "render.py").read_text(encoding="utf-8")
            self.assertNotIn("bbox_inches", source)
            self.assertNotIn("case-packs", source)


if __name__ == "__main__":
    unittest.main()
