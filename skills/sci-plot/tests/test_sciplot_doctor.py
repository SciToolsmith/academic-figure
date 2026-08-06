"""Tests for the lightweight SciPlot doctor."""

from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

import sciplot_doctor as doctor  # noqa: E402
from test_run_implementation_smoke import SmokeFixture  # noqa: E402


def has_pep604_annotation(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    annotations: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.annotation is not None:
            annotations.append(node.annotation)
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
        elif isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) and node.returns is not None:
            annotations.append(node.returns)
    return any(
        isinstance(item, ast.BinOp) and isinstance(item.op, ast.BitOr)
        for annotation in annotations
        for item in ast.walk(annotation)
    )


class DoctorTests(unittest.TestCase):
    def test_healthy_minimal_environment_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SmokeFixture(Path(temporary))
            fixture.add("healthy-v1", requirements=["Python >= 3.9"])
            report = doctor.diagnose(
                skill_root=fixture.root,
                index_path=fixture.index(),
            )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["mode"], "lightweight-no-render")
        self.assertTrue(
            any(
                check["id"] == "DR-CATALOG"
                and check["status"] == "PASS"
                for check in report["checks"]
            )
        )

    def test_missing_profile_is_a_critical_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SmokeFixture(Path(temporary))
            pack = fixture.add("missing-v1")
            (pack / "verification" / "smoke-profile.json").unlink()
            report = doctor.diagnose(
                skill_root=fixture.root,
                index_path=fixture.index(),
            )
        self.assertEqual(report["status"], "FAIL")
        catalog = next(
            item for item in report["checks"] if item["id"] == "DR-CATALOG"
        )
        self.assertEqual(catalog["status"], "FAIL")

    def test_missing_required_package_is_a_critical_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SmokeFixture(Path(temporary))
            fixture.add(
                "dependency-v1",
                requirements=[
                    "Python >= 3.9",
                    "sciplot-package-that-cannot-exist >= 1.0",
                ],
            )
            report = doctor.diagnose(
                skill_root=fixture.root,
                index_path=fixture.index(),
            )
        self.assertEqual(report["status"], "FAIL")
        dependency = next(
            item
            for item in report["checks"]
            if item["id"]
            == "DR-PACKAGE-SCIPLOT-PACKAGE-THAT-CANNOT-EXIST"
        )
        self.assertEqual(dependency["status"], "FAIL")

    def test_report_is_json_serializable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SmokeFixture(Path(temporary))
            fixture.add("serializable-v1")
            report = doctor.diagnose(
                skill_root=fixture.root,
                index_path=fixture.index(),
            )
        self.assertIsInstance(json.loads(json.dumps(report)), dict)

    @mock.patch.object(
        doctor.importlib.metadata,
        "version",
        side_effect=doctor.importlib.metadata.PackageNotFoundError,
    )
    def test_unverifiable_required_version_fails_closed(
        self, _version: mock.Mock
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SmokeFixture(Path(temporary))
            fixture.add(
                "metadata-v1",
                requirements=["Python >= 3.9", "json >= 1.0"],
            )
            report = doctor.diagnose(
                skill_root=fixture.root,
                index_path=fixture.index(),
            )
        self.assertEqual(report["status"], "FAIL")
        package = next(
            item
            for item in report["checks"]
            if item["id"] == "DR-PACKAGE-JSON"
        )
        self.assertIn("cannot verify", package["message"])

    def test_source_avoids_python_310_only_union_annotations(self) -> None:
        self.assertFalse(
            has_pep604_annotation(SCRIPTS / "sciplot_doctor.py")
        )


if __name__ == "__main__":
    unittest.main()
