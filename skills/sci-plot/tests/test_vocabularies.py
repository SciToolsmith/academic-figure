"""Regression tests for SciPlot's machine-vocabulary drift guard."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_vocab_drift.py"
VOCABULARY = ROOT / "references" / "schema-vocabularies.json"
LEXICON = ROOT / "references" / "retrieval-lexicon.json"
CASE_INDEX = ROOT / "references" / "case-index.json"
IMPLEMENTATION_INDEX = ROOT / "implementations" / "implementation-index.json"

SPEC = importlib.util.spec_from_file_location("check_vocab_drift", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
check_vocab_drift = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_vocab_drift)


class VocabularyDriftTests(unittest.TestCase):
    def test_packaged_vocabularies_match_packaged_data(self) -> None:
        report = check_vocab_drift.validate()
        self.assertEqual("PASS", report["status"])
        self.assertGreaterEqual(report["enum_count"], 17)
        self.assertGreaterEqual(report["alias_group_count"], 20)
        self.assertEqual(18, report["case_count"])

    def test_unknown_case_status_is_rejected(self) -> None:
        payload = json.loads(CASE_INDEX.read_text(encoding="utf-8"))
        payload["cases"][0]["audit_status"] = "looks-good"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case-index.json"
            path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "audit_status"):
                check_vocab_drift.validate(
                    VOCABULARY,
                    path,
                    IMPLEMENTATION_INDEX,
                )

    def test_policy_set_must_be_a_subset_of_its_enum(self) -> None:
        payload = json.loads(VOCABULARY.read_text(encoding="utf-8"))
        payload["policy_sets"]["stageable_reuse_level"].append("copy-anything")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schema-vocabularies.json"
            path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "outside reuse_level"):
                check_vocab_drift.validate(
                    path,
                    CASE_INDEX,
                    IMPLEMENTATION_INDEX,
                )

    def test_localized_alias_cannot_map_to_two_canonical_values(self) -> None:
        payload = json.loads(LEXICON.read_text(encoding="utf-8"))
        payload["domain_aliases"]["methods"].append("患者")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "retrieval-lexicon.json"
            path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "maps to both"):
                check_vocab_drift.validate(
                    VOCABULARY,
                    CASE_INDEX,
                    IMPLEMENTATION_INDEX,
                    path,
                )

    def test_alias_collision_cannot_hide_behind_punctuation(self) -> None:
        payload = json.loads(LEXICON.read_text(encoding="utf-8"))
        payload["domain_aliases"]["methods"].append("single/cell")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "retrieval-lexicon.json"
            path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "maps to both"):
                check_vocab_drift.validate(
                    VOCABULARY,
                    CASE_INDEX,
                    IMPLEMENTATION_INDEX,
                    path,
                )

    def test_lexicon_canonical_must_exist_in_the_case_index(self) -> None:
        payload = json.loads(LEXICON.read_text(encoding="utf-8"))
        aliases = payload["data_structure_aliases"].pop(
            "continuous-measurements"
        )
        payload["data_structure_aliases"]["continuous-measurementz"] = aliases
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "retrieval-lexicon.json"
            path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "not present in the case index"):
                check_vocab_drift.validate(
                    VOCABULARY,
                    CASE_INDEX,
                    IMPLEMENTATION_INDEX,
                    path,
                )


if __name__ == "__main__":
    unittest.main()
