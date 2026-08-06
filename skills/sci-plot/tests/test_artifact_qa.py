from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSPECT = ROOT / "scripts" / "inspect_artifacts.py"
BUILD_REPORT = ROOT / "scripts" / "build_qa_report.py"
SEMANTIC_DIFF = ROOT / "scripts" / "semantic_diff.py"


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def make_rgb_png(width: int, height: int, dpi: int = 300) -> bytes:
    rows = []
    for y in range(height):
        pixels = bytearray()
        for x in range(width):
            pixels.extend(((x * 23) % 256, (y * 47) % 256, ((x + y) * 31) % 256))
        rows.append(b"\x00" + bytes(pixels))
    ppm = round(dpi / 0.0254)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + png_chunk(b"pHYs", struct.pack(">IIB", ppm, ppm, 1))
        + png_chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + png_chunk(b"IEND", b"")
    )


def make_structured_pdf() -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 50] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        (
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
            b"/FontDescriptor << /FontFile2 6 0 R >> >>"
        ),
        b"<< /Length 3 >>\nstream\nq Q\nendstream",
        b"<< /Length 1 >>\nstream\nx\nendstream",
    ]
    payload = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{number} 0 obj\n".encode())
        payload.extend(body)
        payload.extend(b"\nendobj\n")
    xref_offset = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        payload.extend(f"{offset:010d} 00000 n \n".encode())
    payload.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    return bytes(payload)


def make_xref_stream_pdf() -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 50] >>",
    ]
    payload = bytearray(b"%PDF-1.5\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{number} 0 obj\n".encode())
        payload.extend(body)
        payload.extend(b"\nendobj\n")
    xref_offset = len(payload)
    offsets.append(xref_offset)
    entries = (
        b"\x00" + (0).to_bytes(4, "big") + (65535).to_bytes(2, "big")
    )
    entries += b"".join(
        b"\x01" + offset.to_bytes(4, "big") + (0).to_bytes(2, "big")
        for offset in offsets
    )
    payload.extend(
        (
            f"4 0 obj\n"
            f"<< /Type /XRef /Size 5 /Root 1 0 R /W [1 4 2] "
            f"/Length {len(entries)} >>\nstream\n"
        ).encode()
    )
    payload.extend(entries)
    payload.extend(
        (
            f"\nendstream\nendobj\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    return bytes(payload)


class ArtifactInspectorTests(unittest.TestCase):
    def run_json(self, command: list[str], expected_code: int = 0) -> dict:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            expected_code,
            msg=f"stdout={completed.stdout}\nstderr={completed.stderr}",
        )
        return json.loads(completed.stdout)

    def test_good_svg_matches_physical_size_and_editable_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "figure.svg"
            path.write_text(
                """<svg xmlns="http://www.w3.org/2000/svg"
                    width="100mm" height="50mm" viewBox="0 0 100 50">
                    <rect x="5" y="5" width="90" height="40" fill="none"/>
                    <text x="10" y="25">evidence</text>
                </svg>""",
                encoding="utf-8",
            )
            report = self.run_json(
                [
                    sys.executable,
                    str(INSPECT),
                    str(path),
                    "--width-mm",
                    "100",
                    "--height-mm",
                    "50",
                    "--require-svg-text",
                ]
            )
        self.assertEqual(report["schema"], "sciplot.artifact-qa/v1")
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["artifacts"][0]["sha256"])
        self.assertEqual(report["artifacts"][0]["editable_text_nodes"], 1)
        self.assertEqual(report["unresolved"], [])

    def test_missing_and_invalid_svg_are_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.svg"
            missing_report = self.run_json(
                [sys.executable, str(INSPECT), str(missing)],
                expected_code=1,
            )
            invalid = Path(directory) / "invalid.svg"
            invalid.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm"',
                encoding="utf-8",
            )
            invalid_report = self.run_json(
                [sys.executable, str(INSPECT), str(invalid), "--require-svg-text"],
                expected_code=1,
            )
        self.assertEqual(missing_report["status"], "FAIL")
        self.assertTrue(any(check["id"] == "AR-01" for check in missing_report["checks"]))
        self.assertEqual(invalid_report["status"], "FAIL")
        self.assertTrue(
            any(
                check["id"] == "AR-02" and check["status"] == "FAIL"
                for check in invalid_report["checks"]
            )
        )

    def test_png_dimensions_and_dpi_are_read_without_required_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preview.png"
            path.write_bytes(make_rgb_png(10, 5, 300))
            report = self.run_json(
                [
                    sys.executable,
                    str(INSPECT),
                    str(path),
                    "--width-px",
                    "10",
                    "--height-px",
                    "5",
                    "--dpi",
                    "300",
                ]
            )
        self.assertIn(report["status"], {"PASS", "WARN"})
        artifact = report["artifacts"][0]
        self.assertEqual((artifact["width_px"], artifact["height_px"]), (10, 5))
        self.assertAlmostEqual(artifact["dpi_x"], 300, delta=0.1)
        self.assertTrue(
            any(
                check["id"] == "AR-04"
                and "DPI metadata matches" in check["evidence"]
                for check in report["checks"]
            )
        )

    def test_nonuniform_opaque_rgba_png_is_not_misread_as_uniform(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is optional")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rgba.png"
            image = Image.new("RGBA", (8, 8), (255, 255, 255, 255))
            image.putpixel((4, 4), (0, 80, 160, 255))
            image.save(path, dpi=(300, 300))
            report = self.run_json(
                [
                    sys.executable,
                    str(INSPECT),
                    str(path),
                    "--width-px",
                    "8",
                    "--height-px",
                    "8",
                    "--dpi",
                    "300",
                ]
            )
        self.assertEqual("PASS", report["status"])
        self.assertTrue(
            any(
                check["id"] == "AR-04"
                and check["status"] == "PASS"
                and "non-uniform" in check["evidence"]
                for check in report["checks"]
            )
        )

    def test_corrupt_png_crc_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrupt.png"
            payload = bytearray(make_rgb_png(10, 5, 300))
            payload[29] ^= 0x01  # Corrupt IHDR CRC without changing the signature.
            path.write_bytes(payload)
            report = self.run_json(
                [sys.executable, str(INSPECT), str(path)],
                expected_code=1,
            )
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any("invalid CRC" in check["evidence"] for check in report["checks"])
        )

    def test_pdf_requires_a_real_cross_reference_structure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = root / "valid.pdf"
            valid.write_bytes(make_structured_pdf())
            valid_report = self.run_json(
                [sys.executable, str(INSPECT), str(valid)]
            )

            xref_stream = root / "xref-stream.pdf"
            xref_stream.write_bytes(make_xref_stream_pdf())
            xref_stream_report = self.run_json(
                [sys.executable, str(INSPECT), str(xref_stream)]
            )

            fake = root / "fake.pdf"
            fake.write_bytes(
                b"%PDF-1.4\n"
                b"/Type /Page /MediaBox [0 0 100 50]\n"
                b"/Font /FontFile2 stream x endstream\n"
                b"xref\ntrailer\nstartxref\n9\n%%EOF\n"
            )
            fake_report = self.run_json(
                [sys.executable, str(INSPECT), str(fake)],
                expected_code=1,
            )

            invalid_prev = root / "invalid-prev.pdf"
            invalid_prev_payload = bytearray(b"%PDF-1.4\n")
            invalid_prev_xref = len(invalid_prev_payload)
            invalid_prev_payload.extend(
                (
                    "xref\n0 1\n0000000000 65535 f \n"
                    "trailer\n<< /Size 1 /Prev 999999 >>\n"
                    f"startxref\n{invalid_prev_xref}\n%%EOF\n"
                ).encode()
            )
            invalid_prev.write_bytes(invalid_prev_payload)
            invalid_prev_report = self.run_json(
                [sys.executable, str(INSPECT), str(invalid_prev)],
                expected_code=1,
            )

            invalid_stream = root / "invalid-xref-stream.pdf"
            invalid_stream_payload = bytearray(b"%PDF-1.5\n")
            invalid_stream_xref = len(invalid_stream_payload)
            invalid_stream_payload.extend(
                (
                    "1 0 obj\n"
                    "<< /Type /XRef /Size 2 /Root 9 0 R "
                    "/W [1 1 1] /Length 1 >>\n"
                    "stream\nx\nendstream\nendobj\n"
                    f"startxref\n{invalid_stream_xref}\n%%EOF\n"
                ).encode()
            )
            invalid_stream.write_bytes(invalid_stream_payload)
            invalid_stream_report = self.run_json(
                [sys.executable, str(INSPECT), str(invalid_stream)],
                expected_code=1,
            )
        self.assertTrue(valid_report["artifacts"][0]["structure_valid"])
        self.assertNotEqual(valid_report["status"], "FAIL")
        self.assertTrue(xref_stream_report["artifacts"][0]["structure_valid"])
        self.assertNotEqual(xref_stream_report["status"], "FAIL")
        self.assertEqual(fake_report["status"], "FAIL")
        self.assertFalse(fake_report["artifacts"][0]["structure_valid"])
        self.assertEqual(invalid_prev_report["status"], "FAIL")
        self.assertFalse(invalid_prev_report["artifacts"][0]["structure_valid"])
        self.assertEqual(invalid_stream_report["status"], "FAIL")
        self.assertFalse(invalid_stream_report["artifacts"][0]["structure_valid"])
        self.assertTrue(
            any(
                check["status"] == "FAIL"
                and "invalid PDF structure" in check["evidence"]
                for check in fake_report["checks"]
            )
        )

    def test_output_cannot_overwrite_an_input_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "figure.svg"
            original = (
                b'<svg xmlns="http://www.w3.org/2000/svg" '
                b'width="10mm" height="10mm" viewBox="0 0 10 10">'
                b'<text x="2" y="5">safe</text></svg>'
            )
            path.write_bytes(original)
            alias = Path(directory) / "artifact-output.json"
            alias.symlink_to(path)
            for output in (path, alias):
                report = self.run_json(
                    [
                        sys.executable,
                        str(INSPECT),
                        str(path),
                        "--output",
                        str(output),
                    ],
                    expected_code=2,
                )
                self.assertEqual(report["status"], "FAIL")
                self.assertEqual(path.read_bytes(), original)
            preserved = path.read_bytes()
        self.assertEqual(preserved, original)

    def test_strict_promotes_optional_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outline-only.svg"
            path.write_text(
                """<svg xmlns="http://www.w3.org/2000/svg"
                    width="10mm" height="10mm" viewBox="0 0 10 10">
                    <path d="M1 1 L9 9"/>
                </svg>""",
                encoding="utf-8",
            )
            report = self.run_json(
                [sys.executable, str(INSPECT), str(path), "--strict"],
                expected_code=1,
            )
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any(check.get("strict_promotion") for check in report["checks"]))


class QaReportBuilderTests(unittest.TestCase):
    def run_json(self, command: list[str], expected_code: int = 0) -> dict:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            expected_code,
            msg=f"stdout={completed.stdout}\nstderr={completed.stderr}",
        )
        return json.loads(completed.stdout)

    def test_merges_contract_and_artifact_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = root / "contract.json"
            artifact = root / "artifact.json"
            contract.write_text(
                json.dumps(
                    {
                        "status": "WARN",
                        "checks": [
                            {
                                "id": "FC-04",
                                "status": "WARN",
                                "message": "target height remains unknown",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            artifact.write_text(
                json.dumps(
                    {
                        "schema": "sciplot.artifact-qa/v1",
                        "status": "PASS",
                        "checks": [
                            {
                                "id": "AR-01",
                                "status": "PASS",
                                "artifact": "figure.svg",
                                "evidence": "dimensions match",
                            }
                        ],
                        "artifacts": [
                            {
                                "path": "figure.svg",
                                "sha256": "abc123",
                                "format": "svg",
                            }
                        ],
                        "unresolved": [],
                    }
                ),
                encoding="utf-8",
            )
            report = self.run_json(
                [
                    sys.executable,
                    str(BUILD_REPORT),
                    str(contract),
                    str(artifact),
                ]
            )
        self.assertEqual(report["schema"], "sciplot.qa-report/v1")
        self.assertEqual(report["status"], "WARN")
        self.assertEqual(report["hashes"]["figure.svg"], "abc123")
        self.assertTrue(any(check["evidence"] == "target height remains unknown" for check in report["checks"]))
        self.assertTrue(any(item["id"] == "FC-04" for item in report["unresolved"]))

    def test_invalid_report_fails_instead_of_becoming_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty-report.json"
            path.write_text('{"status": "PASS"}', encoding="utf-8")
            report = self.run_json(
                [sys.executable, str(BUILD_REPORT), str(path)],
                expected_code=1,
            )
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["checks"][0]["id"], "QA-INPUT")

    def test_explicit_unresolved_status_contributes_to_overall_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            failing = root / "failing.json"
            warning = root / "warning.json"
            base = {
                "status": "PASS",
                "checks": [
                    {
                        "id": "AR-01",
                        "status": "PASS",
                        "evidence": "recorded check passed",
                    }
                ],
            }
            failing.write_text(
                json.dumps(
                    {
                        **base,
                        "unresolved": [
                            {
                                "id": "AR-99",
                                "status": "FAIL",
                                "evidence": "artifact cannot be verified",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            warning.write_text(
                json.dumps(
                    {
                        **base,
                        "checks": base["checks"]
                        + [
                            {
                                "id": "AR-DUP",
                                "status": "WARN",
                                "evidence": "already represented warning",
                            }
                        ],
                        "unresolved": [
                            {
                                "id": "AR-98",
                                "status": "WARN",
                                "evidence": "manual review remains",
                            },
                            {
                                "id": "AR-DUP",
                                "status": "WARN",
                                "evidence": "already represented warning",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            fail_report = self.run_json(
                [sys.executable, str(BUILD_REPORT), str(failing)],
                expected_code=1,
            )
            warn_report = self.run_json(
                [sys.executable, str(BUILD_REPORT), str(warning)]
            )
        self.assertEqual(fail_report["status"], "FAIL")
        self.assertEqual(fail_report["layers"][0]["observed_status"], "FAIL")
        self.assertEqual(fail_report["summary"]["fail"], 1)
        self.assertTrue(
            any(check.get("unresolved_input") for check in fail_report["checks"])
        )
        self.assertEqual(warn_report["status"], "WARN")
        self.assertEqual(warn_report["layers"][0]["observed_status"], "WARN")
        self.assertEqual(warn_report["summary"]["warn"], 2)

    def test_output_cannot_overwrite_an_input_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            original = json.dumps(
                {
                    "status": "PASS",
                    "checks": [
                        {
                            "id": "AR-01",
                            "status": "PASS",
                            "evidence": "safe",
                        }
                    ],
                }
            )
            path.write_text(original, encoding="utf-8")
            alias = Path(directory) / "report-alias.json"
            os.link(path, alias)
            for output in (path, alias):
                report = self.run_json(
                    [
                        sys.executable,
                        str(BUILD_REPORT),
                        str(path),
                        "--output",
                        str(output),
                    ],
                    expected_code=2,
                )
                self.assertEqual(report["status"], "FAIL")
                self.assertEqual(path.read_text(encoding="utf-8"), original)
            preserved = path.read_text(encoding="utf-8")
        self.assertEqual(preserved, original)

    def test_malformed_unresolved_field_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(
                json.dumps(
                    {
                        "status": "PASS",
                        "checks": [
                            {
                                "id": "AR-01",
                                "status": "PASS",
                                "evidence": "recorded check passed",
                            }
                        ],
                        "unresolved": {
                            "status": "FAIL",
                            "evidence": "wrong container type",
                        },
                    }
                ),
                encoding="utf-8",
            )
            report = self.run_json(
                [sys.executable, str(BUILD_REPORT), str(path)],
                expected_code=1,
            )
        self.assertEqual(report["status"], "FAIL")
        self.assertGreater(report["summary"]["fail"], 0)
        self.assertTrue(
            any(
                check["id"] == "QA-INPUT"
                and "unresolved field must be an array" in check["evidence"]
                for check in report["checks"]
            )
        )

    def test_strict_recomputes_layer_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(
                json.dumps(
                    {
                        "status": "WARN",
                        "checks": [
                            {
                                "id": "AR-01",
                                "status": "WARN",
                                "evidence": "manual review remains",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            report = self.run_json(
                [
                    sys.executable,
                    str(BUILD_REPORT),
                    str(path),
                    "--strict",
                ],
                expected_code=1,
            )
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["layers"][0]["observed_status"], "FAIL")
        self.assertEqual(report["summary"]["fail"], 1)


class SemanticDiffOutputSafetyTests(unittest.TestCase):
    def test_output_cannot_overwrite_before_or_after(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = root / "before.json"
            after = root / "after.json"
            before_payload = json.dumps({"question": {"analysis_unit": "participant"}})
            after_payload = json.dumps({"question": {"analysis_unit": "row"}})
            before.write_text(before_payload, encoding="utf-8")
            after.write_text(after_payload, encoding="utf-8")
            before_alias = root / "before-alias.json"
            os.link(before, before_alias)

            for output in (before, after, before_alias):
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(SEMANTIC_DIFF),
                        str(before),
                        str(after),
                        "--output",
                        str(output),
                    ],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(
                    completed.returncode,
                    2,
                    msg=f"stdout={completed.stdout}\nstderr={completed.stderr}",
                )
                self.assertEqual(json.loads(completed.stdout)["status"], "FAIL")
                self.assertEqual(before.read_text(encoding="utf-8"), before_payload)
                self.assertEqual(after.read_text(encoding="utf-8"), after_payload)


if __name__ == "__main__":
    unittest.main()
