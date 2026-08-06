"""Integrity and safety tests for SciPlot's reference source packs."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEMANTIC_INDEX = ROOT / "references" / "case-index.json"
ASSET_INDEX = ROOT / "references" / "case-assets.json"
STAGER = ROOT / "scripts" / "stage_case.py"
DEMO_GENERATOR = ROOT / "scripts" / "generate_case_demo.py"


def run(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


class CaseAssetCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.semantic = json.loads(SEMANTIC_INDEX.read_text(encoding="utf-8"))
        cls.assets = json.loads(ASSET_INDEX.read_text(encoding="utf-8"))

    def test_asset_catalog_matches_all_semantic_cases(self) -> None:
        semantic_ids = {item["id"] for item in self.semantic["cases"]}
        asset_ids = {item["id"] for item in self.assets["cases"]}
        self.assertEqual(len(semantic_ids), 18)
        self.assertEqual(semantic_ids, asset_ids)

    def test_every_pack_contains_python_and_r_source(self) -> None:
        for item in self.assets["cases"]:
            pack = ROOT / item["pack"]
            self.assertTrue(pack.is_dir(), item["id"])
            self.assertEqual(set(item["entrypoints"]), {"python", "r"})
            for filename in item["entrypoints"].values():
                self.assertTrue((pack / filename).is_file(), item["id"])

    def test_all_python_sources_compile_without_execution(self) -> None:
        for item in self.assets["cases"]:
            source = ROOT / item["pack"] / item["entrypoints"]["python"]
            compile(source.read_text(encoding="utf-8"), str(source), "exec")

    def test_sources_do_not_contain_network_or_destructive_shortcuts(self) -> None:
        forbidden = (
            "requests.",
            "urllib",
            "download.file",
            "install.packages",
            "subprocess",
            "os.system",
            "shutil.rmtree",
            "file.remove",
        )
        findings: list[str] = []
        for item in self.assets["cases"]:
            pack = ROOT / item["pack"]
            for source in pack.iterdir():
                text = source.read_text(encoding="utf-8").lower()
                for token in forbidden:
                    if token in text:
                        findings.append(f"{source.relative_to(ROOT)}: {token}")
        self.assertEqual(findings, [])

    def test_stager_validates_catalog(self) -> None:
        completed = run(str(STAGER), "--validate-only")
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["cases"], 18)


class CaseStagingTests(unittest.TestCase):
    def test_staging_copies_one_backend_and_writes_mapping_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workdir = Path(temp) / "rf-0001"
            completed = run(
                str(STAGER),
                "rf-0001",
                "--backend",
                "python",
                "--reuse-level",
                "structural",
                "--workdir",
                str(workdir),
            )
            result = json.loads(completed.stdout)
            ledger = json.loads(
                (workdir / "case-adaptation.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result["status"], "staged")
            self.assertEqual(ledger["execution_state"], "mapping-required")
            self.assertEqual(ledger["inputs"]["field_mapping"], [])
            self.assertTrue(ledger["source"]["immutable"])
            self.assertTrue((workdir / "faceted_stacked_bar.py").is_file())
            self.assertFalse((workdir / "faceted_stacked_bar.R").exists())

    def test_conditional_case_requires_repair_gate_for_structural_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            completed = run(
                str(STAGER),
                "rf-0104",
                "--backend",
                "python",
                "--reuse-level",
                "structural",
                "--workdir",
                str(Path(temp) / "blocked"),
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("repair gate must be satisfied", completed.stderr)

    def test_stager_refuses_a_nonempty_workdir(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workdir = Path(temp) / "occupied"
            workdir.mkdir()
            (workdir / "user-file.txt").write_text("preserve", encoding="utf-8")
            completed = run(
                str(STAGER),
                "rf-0001",
                "--backend",
                "python",
                "--workdir",
                str(workdir),
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("workdir must be empty", completed.stderr)
            self.assertEqual(
                (workdir / "user-file.txt").read_text(encoding="utf-8"),
                "preserve",
            )


class CaseDemoTests(unittest.TestCase):
    def test_rf_0001_demo_is_deterministic_and_explicitly_nonproduction(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            completed = run(
                str(DEMO_GENERATOR),
                "rf-0001",
                "--output-dir",
                temp,
            )
            result = json.loads(completed.stdout)
            path = Path(result["files"][0])
            with path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            manifest = json.loads(
                (Path(temp) / "demo-data.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(rows), 240)
            self.assertEqual({row["source_seed"] for row in rows}, {"123"})
            self.assertTrue(manifest["synthetic"])
            self.assertFalse(manifest["production_use_allowed"])

    def test_rf_0001_rejects_a_seed_the_reference_would_reject(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            completed = run(
                str(DEMO_GENERATOR),
                "rf-0001",
                "--output-dir",
                temp,
                "--seed",
                "124",
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("requires --seed 123", completed.stderr)

    def test_rf_0178_demo_covers_all_groups_and_positive_log_domain(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            completed = run(
                str(DEMO_GENERATOR),
                "rf-0178",
                "--output-dir",
                temp,
            )
            result = json.loads(completed.stdout)
            with Path(result["files"][0]).open(
                "r", encoding="utf-8", newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 135)
            self.assertEqual({row["type"] for row in rows}, {"WGS", "MAG", "SAG"})
            self.assertTrue(all(float(row["length"]) > 0 for row in rows))
            self.assertTrue(all(float(row["number_of_cds"]) > 0 for row in rows))


if __name__ == "__main__":
    unittest.main()
