"""Regression tests for Figure Contract ↔ Render Manifest reconciliation."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "scripts" / "validate_delivery.py"

SPEC = importlib.util.spec_from_file_location(
    "validate_delivery",
    VALIDATOR_PATH,
)
assert SPEC is not None and SPEC.loader is not None
validate_delivery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_delivery)


class DeliveryValidatorTests(unittest.TestCase):
    def fixture(
        self,
        directory: Path,
    ) -> tuple[Path, Path, Path]:
        contract_path = directory / "figure-contract.json"
        contract_path.write_text(
            json.dumps(
                {
                    "contract_version": 1,
                    "target": {
                        "width_mm": 100,
                        "height_mm": 50,
                        "formats": ["svg", "png"],
                        "primary_format": "svg",
                        "preview_format": "png",
                        "resolution_dpi": 300,
                    },
                }
            ),
            encoding="utf-8",
        )
        artifacts: list[dict[str, object]] = []
        for name, output_format, content in (
            ("figure.svg", "svg", b"<svg/>"),
            ("figure.png", "png", b"not-a-real-png"),
            ("analysis.csv", "csv", b"a,b\n1,2\n"),
        ):
            path = directory / name
            path.write_bytes(content)
            artifacts.append(
                {
                    "file": name,
                    "format": output_format,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "bytes": len(content),
                }
            )
        manifest_path = directory / "render-manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "sciplot.render-manifest/v1",
                    "figure_contract": {
                        "sha256": hashlib.sha256(
                            contract_path.read_bytes()
                        ).hexdigest()
                    },
                    "figure": {
                        "width_mm": 100,
                        "height_mm": 50,
                        "dpi_for_raster": 300,
                    },
                    "artifacts": artifacts,
                }
            ),
            encoding="utf-8",
        )
        return contract_path, manifest_path, directory

    def test_matching_contract_manifest_and_files_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            contract, manifest, artifact_dir = self.fixture(Path(temp))
            result = validate_delivery.validate_delivery(
                contract,
                manifest,
                artifact_dir,
            )
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(
                {item["id"] for item in result["checks"]},
                {"DV-01", "DV-02", "DV-03", "DV-04"},
            )

    def test_missing_format_and_wrong_dpi_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            contract, manifest, artifact_dir = self.fixture(Path(temp))
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["artifacts"] = [
                item
                for item in payload["artifacts"]
                if item["format"] != "png"
            ]
            payload["figure"]["dpi_for_raster"] = 150
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            result = validate_delivery.validate_delivery(
                contract,
                manifest,
                artifact_dir,
            )
            self.assertEqual(result["status"], "FAIL")
            failed_ids = {
                item["id"]
                for item in result["checks"]
                if item["status"] == "FAIL"
            }
            self.assertIn("DV-02", failed_ids)
            self.assertIn("DV-03", failed_ids)

    def test_unbound_or_tampered_artifact_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            contract, manifest, artifact_dir = self.fixture(Path(temp))
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["figure_contract"]["sha256"] = "0" * 64
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            (artifact_dir / "figure.svg").write_text(
                "<svg><text>changed</text></svg>",
                encoding="utf-8",
            )
            result = validate_delivery.validate_delivery(
                contract,
                manifest,
                artifact_dir,
            )
            self.assertEqual(result["status"], "FAIL")
            failed_ids = {
                item["id"]
                for item in result["checks"]
                if item["status"] == "FAIL"
            }
            self.assertIn("DV-01", failed_ids)
            self.assertIn("DV-04", failed_ids)

    def test_cli_refuses_to_overwrite_an_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            contract, manifest, artifact_dir = self.fixture(Path(temp))
            completed = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR_PATH),
                    "--contract",
                    str(contract),
                    "--manifest",
                    str(manifest),
                    "--artifact-dir",
                    str(artifact_dir),
                    "--output",
                    str(manifest),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("must not overwrite", completed.stdout)


if __name__ == "__main__":
    unittest.main()
