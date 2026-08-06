"""Regression tests for SciPlot's executable evaluation protocol."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "run_evals.py"
CATALOG = SKILL_ROOT / "evals" / "evals.json"


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=SKILL_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def parsed_stdout(completed: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(completed.stdout)


def complete_behavioral_package() -> dict:
    completed = run_cli("template")
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    payload = parsed_stdout(completed)
    payload["run_id"] = "external-forward-test-001"
    payload["producer"]["name"] = "test-external-agent"
    for result in payload["results"]:
        result["response"] = f"External response for {result['eval_id']}"
        for assertion in result["assertions"]:
            assertion["status"] = "pass"
            assertion["evidence"] = (
                f"External trace evidence for {result['eval_id']} "
                f"{assertion['assertion_id']}"
            )
    return payload


class EvalCatalogTests(unittest.TestCase):
    def test_catalog_separates_deterministic_and_behavioral_surfaces(self) -> None:
        payload = json.loads(CATALOG.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], "sciplot.eval-catalog/v2")
        self.assertFalse(
            payload["evaluation_boundary"]["runner_invokes_external_agent"]
        )
        self.assertEqual(
            payload["protocol"]["expected_assertion_id_template"],
            "expected-{position:02d}",
        )
        self.assertEqual(len(payload["deterministic_probes"]), 5)
        self.assertEqual(len(payload["evals"]), 15)
        for item in payload["evals"]:
            self.assertTrue(item["prompt"].strip())
            self.assertTrue(all(value.strip() for value in item["expected"]))

    def test_deterministic_mode_executes_direct_probes(self) -> None:
        completed = run_cli("deterministic")
        self.assertEqual(completed.returncode, 0, completed.stdout)
        report = parsed_stdout(completed)
        self.assertEqual(report["schema"], "sciplot.eval-report/v1")
        self.assertEqual(report["mode"], "deterministic")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(
            report["assessment_basis"], "direct-repository-probes"
        )
        self.assertFalse(report["external_agent_invoked_by_runner"])
        self.assertEqual(report["summary"]["probes_pass"], 5)
        self.assertEqual(report["summary"]["assertions_fail"], 0)

    def test_template_is_bound_to_exact_catalog_and_starts_unassessed(self) -> None:
        completed = run_cli("template")
        self.assertEqual(completed.returncode, 0, completed.stdout)
        payload = parsed_stdout(completed)
        expected_digest = hashlib.sha256(CATALOG.read_bytes()).hexdigest()
        self.assertEqual(payload["catalog_sha256"], expected_digest)
        self.assertEqual(payload["producer"]["kind"], "external-agent")
        self.assertEqual(len(payload["results"]), 15)
        statuses = {
            assertion["status"]
            for result in payload["results"]
            for assertion in result["assertions"]
        }
        self.assertEqual(statuses, {"not-assessed"})

    def test_complete_external_behavioral_package_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            results_path = Path(temporary) / "behavioral.json"
            results_path.write_text(
                json.dumps(complete_behavioral_package(), ensure_ascii=False),
                encoding="utf-8",
            )
            completed = run_cli(
                "behavioral", "--results", str(results_path)
            )
        self.assertEqual(completed.returncode, 0, completed.stdout)
        report = parsed_stdout(completed)
        self.assertEqual(report["mode"], "behavioral")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(
            report["assessment_basis"], "externally-produced-agent-results"
        )
        self.assertFalse(report["external_agent_invoked_by_runner"])
        self.assertFalse(
            report["behavioral_assertions_independently_verified_by_runner"]
        )
        self.assertEqual(report["summary"]["evals_pass"], 15)
        self.assertEqual(report["summary"]["assertions_missing"], 0)

    def test_unfilled_template_cannot_masquerade_as_a_completed_run(self) -> None:
        template = parsed_stdout(run_cli("template"))
        with tempfile.TemporaryDirectory() as temporary:
            results_path = Path(temporary) / "template.json"
            results_path.write_text(
                json.dumps(template, ensure_ascii=False), encoding="utf-8"
            )
            completed = run_cli(
                "behavioral", "--results", str(results_path)
            )
        self.assertEqual(completed.returncode, 2, completed.stdout)
        report = parsed_stdout(completed)
        self.assertEqual(report["assessment_basis"], "input-validation")
        self.assertIn("run_id", report["error"])

    def test_missing_eval_is_reported_and_fails(self) -> None:
        payload = complete_behavioral_package()
        missing_id = payload["results"].pop()["eval_id"]
        with tempfile.TemporaryDirectory() as temporary:
            results_path = Path(temporary) / "incomplete.json"
            results_path.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            completed = run_cli(
                "behavioral", "--results", str(results_path)
            )
        self.assertEqual(completed.returncode, 1, completed.stdout)
        report = parsed_stdout(completed)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any(missing_id in error for error in report["package_errors"])
        )
        self.assertGreater(report["summary"]["assertions_missing"], 0)

    def test_missing_expected_assertion_is_reported_and_fails(self) -> None:
        payload = complete_behavioral_package()
        removed = payload["results"][0]["assertions"].pop()["assertion_id"]
        target_id = payload["results"][0]["eval_id"]
        with tempfile.TemporaryDirectory() as temporary:
            results_path = Path(temporary) / "missing-assertion.json"
            results_path.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            completed = run_cli(
                "behavioral", "--results", str(results_path)
            )
        self.assertEqual(completed.returncode, 1, completed.stdout)
        report = parsed_stdout(completed)
        target = next(
            item for item in report["evals"] if item["eval_id"] == target_id
        )
        self.assertEqual(target["coverage"], "incomplete")
        self.assertTrue(
            any(
                assertion["assertion_id"] == removed
                and assertion["status"] == "missing"
                for assertion in target["assertions"]
            )
        )

    def test_wrong_catalog_digest_is_an_input_error(self) -> None:
        payload = complete_behavioral_package()
        payload["catalog_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            results_path = Path(temporary) / "wrong-digest.json"
            results_path.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            completed = run_cli(
                "behavioral", "--results", str(results_path)
            )
        self.assertEqual(completed.returncode, 2, completed.stdout)
        report = parsed_stdout(completed)
        self.assertEqual(report["assessment_basis"], "input-validation")
        self.assertIn("catalog_sha256", report["error"])

    def test_probe_script_path_traversal_is_rejected(self) -> None:
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        unsafe = copy.deepcopy(catalog)
        unsafe["deterministic_probes"][0]["script"] = "../outside.py"
        with tempfile.TemporaryDirectory() as temporary:
            catalog_path = Path(temporary) / "unsafe-catalog.json"
            catalog_path.write_text(
                json.dumps(unsafe, ensure_ascii=False), encoding="utf-8"
            )
            completed = run_cli(
                "deterministic", "--catalog", str(catalog_path)
            )
        self.assertEqual(completed.returncode, 2, completed.stdout)
        report = parsed_stdout(completed)
        self.assertFalse(report["external_agent_invoked_by_runner"])
        self.assertIn("escapes the skill root", report["error"])

    def test_probe_cannot_override_a_repository_input_path(self) -> None:
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        unsafe = copy.deepcopy(catalog)
        unsafe["deterministic_probes"][0]["args"] = [
            "--index=/tmp/untrusted-index.json",
            "--json",
        ]
        with tempfile.TemporaryDirectory() as temporary:
            catalog_path = Path(temporary) / "unsafe-arguments.json"
            catalog_path.write_text(
                json.dumps(unsafe, ensure_ascii=False), encoding="utf-8"
            )
            completed = run_cli(
                "deterministic", "--catalog", str(catalog_path)
            )
        self.assertEqual(completed.returncode, 2, completed.stdout)
        report = parsed_stdout(completed)
        self.assertIn("may not override repository input paths", report["error"])

    def test_output_cannot_overwrite_catalog_input(self) -> None:
        original = CATALOG.read_bytes()
        completed = run_cli(
            "template", "--output", str(CATALOG)
        )
        self.assertEqual(completed.returncode, 2, completed.stdout)
        self.assertEqual(CATALOG.read_bytes(), original)
        report = parsed_stdout(completed)
        self.assertIn("must not overwrite an input file", report["error"])


if __name__ == "__main__":
    unittest.main()
