from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "semantic_diff.py"
SPEC = importlib.util.spec_from_file_location("semantic_diff", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
classify = MODULE.classify
compare = MODULE.compare
is_allowed = MODULE.is_allowed


class SemanticDiffTests(unittest.TestCase):
    def test_visual_change_is_not_semantic(self) -> None:
        before = {"visual_system": {"emphasis": "raw points"}}
        after = {"visual_system": {"emphasis": "interval"}}
        changes = compare(before, after)
        self.assertEqual(changes[0]["class"], "implementation")

    def test_analysis_unit_change_is_semantic(self) -> None:
        before = {"panels": [{"id": "a", "analysis_unit": "participant"}]}
        after = {"panels": [{"id": "a", "analysis_unit": "row"}]}
        changes = compare(before, after)
        self.assertEqual(changes[0]["class"], "semantic")

    def test_statistics_change_is_semantic(self) -> None:
        self.assertEqual(classify("panels[0].statistics.test_or_model"), "semantic")

    def test_panel_purpose_fields_are_semantic(self) -> None:
        for field in ("question", "evidence_role", "unique_contribution"):
            with self.subTest(field=field):
                self.assertEqual(classify(f"panels[0].{field}"), "semantic")

    def test_allow_prefix_is_explicit(self) -> None:
        self.assertTrue(
            is_allowed("panels[0].statistics.test_or_model", ["panels[0].statistics"])
        )
        self.assertFalse(is_allowed("data_integrity.sampling", ["visual_system"]))

    def test_cli_emits_mergeable_schema_and_check_array(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = root / "before.json"
            after = root / "after.json"
            output = root / "diff.json"
            before.write_text(
                json.dumps({"visual_system": {"emphasis": "raw points"}}),
                encoding="utf-8",
            )
            after.write_text(
                json.dumps({"visual_system": {"emphasis": "interval"}}),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(before),
                    str(after),
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "sciplot.semantic-diff/v1")
            self.assertEqual(payload["checks"][0]["id"], "RV-01")
            self.assertEqual(payload["status"], "PASS")

    def test_cli_fails_on_unapproved_semantic_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = root / "before.json"
            after = root / "after.json"
            before.write_text(
                json.dumps({"question": {"analysis_unit": "participant"}}),
                encoding="utf-8",
            )
            after.write_text(
                json.dumps({"question": {"analysis_unit": "row"}}),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), str(before), str(after)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 1, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "FAIL")
            self.assertEqual(payload["checks"][0]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
