"""Tests for the index-driven native implementation smoke runner."""

from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_implementation_smoke as smoke  # noqa: E402


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


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


class SmokeFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.entries: list[dict[str, str]] = []
        (root / "implementations").mkdir(parents=True)
        (root / "references").mkdir()

    def add(
        self,
        implementation_id: str,
        *,
        status: str = "verified",
        renderer_exit: int = 0,
        profile: Optional[dict] = None,
        entrypoint: str = "render.py",
        requirements: Optional[list[str]] = None,
    ) -> Path:
        pack = (
            self.root
            / "implementations"
            / "python"
            / implementation_id
        )
        pack.mkdir(parents=True)
        renderer = pack / "render.py"
        renderer.write_text(
            "import json, sys\n"
            f"print(json.dumps({{'status': 'test'}}))\n"
            f"raise SystemExit({renderer_exit})\n",
            encoding="utf-8",
        )
        (pack / "examples").mkdir()
        (pack / "examples" / "demo.csv").write_text("x\n1\n", encoding="utf-8")
        write_json(pack / "examples" / "demo-data.json", {"synthetic": True})
        contract_name = f"{implementation_id}.contract.json"
        write_json(
            self.root / "references" / contract_name,
            {"contract_version": 1, "target": {}},
        )
        manifest_relative = (
            f"implementations/python/{implementation_id}/implementation.json"
        )
        write_json(
            pack / "implementation.json",
            {
                "id": implementation_id,
                "version": "1.0.0",
                "status": status,
                "backend": {
                    "language": "python",
                    "entrypoint": entrypoint,
                    "requires": requirements or ["Python >= 3.9"],
                },
                "verification": {
                    "figure_contract": f"references/{contract_name}"
                },
                "outputs": {
                    "basename": "figure",
                    "formats": ["svg"],
                    "manifest": "figure.manifest.json",
                    "data_validation": "data-validation.json",
                },
            },
        )
        if profile is None:
            profile = {
                "schema_version": smoke.PROFILE_SCHEMA,
                "argv": [
                    "render.py",
                    "--input",
                    (
                        f"implementations/python/{implementation_id}"
                        "/examples/demo.csv"
                    ),
                    "--data-manifest",
                    (
                        f"implementations/python/{implementation_id}"
                        "/examples/demo-data.json"
                    ),
                    "--figure-contract",
                    f"references/{contract_name}",
                    "--output-dir",
                    smoke.OUTPUT_PLACEHOLDER,
                ],
            }
        write_json(pack / "verification" / "smoke-profile.json", profile)
        self.entries.append(
            {
                "id": implementation_id,
                "version": "1.0.0",
                "status": status,
                "backend": "python",
                "manifest": manifest_relative,
            }
        )
        return pack

    def index(self) -> Path:
        path = self.root / "implementations" / "implementation-index.json"
        write_json(path, {"implementations": self.entries})
        return path


class ProfileSafetyTests(unittest.TestCase):
    def test_discovers_only_verified_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SmokeFixture(Path(temporary))
            fixture.add("verified-v1")
            fixture.add("candidate-v1", status="candidate")
            targets = smoke.discover_verified(
                skill_root=fixture.root,
                index_path=fixture.index(),
            )
        self.assertEqual(
            [target.implementation_id for target in targets],
            ["verified-v1"],
        )

    def test_missing_profile_is_a_configuration_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SmokeFixture(Path(temporary))
            pack = fixture.add("missing-profile-v1")
            (pack / "verification" / "smoke-profile.json").unlink()
            with self.assertRaisesRegex(
                smoke.SmokeConfigurationError, "has no.*smoke-profile"
            ):
                smoke.discover_verified(
                    skill_root=fixture.root,
                    index_path=fixture.index(),
                )

    def test_unsafe_profile_tokens_are_rejected(self) -> None:
        base_argv = [
            "render.py",
            "--input",
            "implementations/python/unsafe-v1/examples/demo.csv",
            "--data-manifest",
            (
                "implementations/python/unsafe-v1/"
                "examples/demo-data.json"
            ),
            "--figure-contract",
            "references/unsafe-v1.contract.json",
            "--output-dir",
            smoke.OUTPUT_PLACEHOLDER,
        ]
        cases = {
            "absolute": (2, "/tmp/demo.csv", "absolute|unsafe path"),
            "traversal": (2, "../demo.csv", "unsafe path"),
            "equals-absolute": (
                1,
                "--input=/tmp/demo.csv",
                "unsafe path",
            ),
            "equals-traversal": (
                1,
                "--input=../demo.csv",
                "unsafe path",
            ),
            "shell": (2, "demo.csv; touch pwned", "shell metacharacter"),
        }
        for label, (position, value, error) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                fixture = SmokeFixture(Path(temporary))
                argv = list(base_argv)
                argv[position] = value
                fixture.add(
                    "unsafe-v1",
                    profile={
                        "schema_version": smoke.PROFILE_SCHEMA,
                        "argv": argv,
                    },
                )
                with self.assertRaisesRegex(
                    smoke.SmokeConfigurationError, error
                ):
                    smoke.discover_verified(
                        skill_root=fixture.root,
                        index_path=fixture.index(),
                    )

    def test_entrypoint_cannot_escape_its_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SmokeFixture(Path(temporary))
            fixture.add("escape-v1", entrypoint="../outside.py")
            with self.assertRaisesRegex(
                smoke.SmokeConfigurationError, "entrypoint is unsafe"
            ):
                smoke.discover_verified(
                    skill_root=fixture.root,
                    index_path=fixture.index(),
                )

    def test_output_placeholder_must_be_unique_and_standalone(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SmokeFixture(Path(temporary))
            pack = fixture.add("duplicate-output-v1")
            profile_path = pack / "verification" / "smoke-profile.json"
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["argv"].extend(["--another", smoke.OUTPUT_PLACEHOLDER])
            write_json(profile_path, profile)
            with self.assertRaisesRegex(
                smoke.SmokeConfigurationError, "exactly once"
            ):
                smoke.discover_verified(
                    skill_root=fixture.root,
                    index_path=fixture.index(),
                )


class RunnerTests(unittest.TestCase):
    @mock.patch.object(
        smoke,
        "run_qa_pipeline",
        return_value={"status": "PASS", "qa_summary": {"fail": 0}},
    )
    def test_dynamic_run_emits_machine_report(self, _qa: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = SmokeFixture(root / "skill")
            fixture.add("alpha-v1")
            fixture.add("beta-v1")
            report = smoke.run_all(
                skill_root=fixture.root,
                index_path=fixture.index(),
                output_root=root / "outputs",
            )
        self.assertEqual(report["status"], "PASS")
        self.assertFalse(report["shell_invoked"])
        self.assertEqual(report["summary"], {
            "verified": 2,
            "passed": 2,
            "failed": 0,
        })
        self.assertEqual(
            [item["id"] for item in report["implementations"]],
            ["alpha-v1", "beta-v1"],
        )

    @mock.patch.object(smoke, "run_qa_pipeline")
    def test_renderer_failure_is_not_ignored(self, qa: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = SmokeFixture(root / "skill")
            fixture.add("broken-v1", renderer_exit=7)
            report = smoke.run_all(
                skill_root=fixture.root,
                index_path=fixture.index(),
                output_root=root / "outputs",
            )
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["summary"]["failed"], 1)
        self.assertEqual(
            report["implementations"][0]["renderer"]["returncode"], 7
        )
        qa.assert_not_called()

    @mock.patch.object(smoke, "run_qa_pipeline")
    def test_symbolic_link_output_directory_is_rejected(
        self, qa: mock.Mock
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = SmokeFixture(root / "skill")
            fixture.add("linked-v1")
            output_root = root / "outputs"
            output_root.mkdir()
            outside = root / "outside"
            outside.mkdir()
            (output_root / "linked-v1").symlink_to(
                outside, target_is_directory=True
            )
            report = smoke.run_all(
                skill_root=fixture.root,
                index_path=fixture.index(),
                output_root=output_root,
            )
        self.assertEqual(report["status"], "FAIL")
        self.assertIn(
            "symbolic-link",
            report["implementations"][0]["error"],
        )
        qa.assert_not_called()

    def test_source_avoids_python_310_only_union_annotations(self) -> None:
        self.assertFalse(
            has_pep604_annotation(SCRIPTS / "run_implementation_smoke.py")
        )


if __name__ == "__main__":
    unittest.main()
