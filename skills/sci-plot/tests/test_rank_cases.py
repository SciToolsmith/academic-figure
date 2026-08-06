"""Regression tests for SciPlot's optional case retriever."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "rank_cases.py"
INDEX = SKILL_ROOT / "references" / "case-index.json"
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from rank_cases import word_tokens  # noqa: E402


def run_ranker(*arguments: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), *arguments, "--json"],
        cwd=SKILL_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def run_text_ranker(*arguments: str) -> str:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=SKILL_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


class CaseIndexTests(unittest.TestCase):
    def test_status_axes_are_orthogonal_and_catalog_has_no_task_reuse_level(self) -> None:
        payload = json.loads(INDEX.read_text(encoding="utf-8"))
        self.assertNotIn("controlled_vocabulary", payload)
        lexicon = SKILL_ROOT / payload["retrieval_lexicon"]
        self.assertTrue(lexicon.is_file())
        for case in payload["cases"]:
            self.assertIn("audit_status", case)
            self.assertIn("implementation_status", case)
            self.assertNotIn("catalog_status", case)
            self.assertNotIn("reuse_level", case)
            if case["audit_status"] == "conditional":
                self.assertTrue(case.get("repair_gate"))


class RankCasesTests(unittest.TestCase):
    def test_cjk_tokens_retain_the_run_and_add_bigrams(self) -> None:
        tokens = word_tokens("比较各组原始观测")
        self.assertIn("比较各组原始观测", tokens)
        self.assertIn("比较", tokens)
        self.assertIn("各组", tokens)
        self.assertIn("原始", tokens)
        self.assertIn("观测", tokens)

    def test_chinese_paraphrase_retrieves_raw_distribution_case(self) -> None:
        outcome = run_ranker(
            "--query",
            "比较不同组的连续测量值，同时让每个原始观测可见",
            "--include-conditional",
        )
        self.assertEqual("matched", outcome["retrieval_status"])
        self.assertEqual("rf-0104", outcome["matches"][0]["id"])
        reasons = outcome["matches"][0]["match_reasons"]
        self.assertTrue(
            any(
                reason["match_type"] == "controlled-alias"
                and reason["case_value"] == "continuous measurements"
                for reason in reasons
            )
        )
        self.assertTrue(
            any(
                reason["match_type"] == "token-overlap"
                and reason["case_value"] == "原始点"
                for reason in reasons
            )
        )

    def test_survival_query_retrieves_kaplan_meier_case(self) -> None:
        outcome = run_ranker(
            "--query",
            "survival with censoring, a risk table, and group comparison",
        )
        self.assertEqual("matched", outcome["retrieval_status"])
        self.assertEqual("rf-0018", outcome["matches"][0]["id"])
        self.assertTrue(outcome["has_production_ready_match"])
        self.assertIn("match_reasons", outcome["matches"][0])

    def test_generic_measurement_word_does_not_block_survival_structure(self) -> None:
        outcome = run_ranker(
            "--query",
            "患者的生存时间测量值和删失信息",
        )
        self.assertEqual("matched", outcome["retrieval_status"])
        self.assertEqual("rf-0018", outcome["matches"][0]["id"])

    def test_paired_natural_language_alias_retrieves_paired_case(self) -> None:
        outcome = run_ranker(
            "--query",
            "同一批患者治疗前后重复测量，需要保留每个人的变化方向",
            "--include-conditional",
        )
        self.assertEqual("matched", outcome["retrieval_status"])
        self.assertEqual("rf-0173", outcome["matches"][0]["id"])
        alias_reasons = [
            reason
            for reason in outcome["matches"][0]["match_reasons"]
            if reason["match_type"] == "controlled-alias"
        ]
        self.assertTrue(
            any(reason["case_value"] == "paired" for reason in alias_reasons)
        )
        self.assertEqual(
            "repair-required", outcome["matches"][0]["reuse_readiness"]
        )

    def test_irrelevant_topology_does_not_match_embedding(self) -> None:
        outcome = run_ranker(
            "--query",
            "wormhole topology in relativistic spacetime",
        )
        self.assertEqual("no-suitable-case", outcome["retrieval_status"])
        self.assertTrue(outcome["no_suitable_case"])
        self.assertEqual([], outcome["matches"])

    def test_irrelevant_query_with_structure_is_constraint_only(self) -> None:
        outcome = run_ranker(
            "--query",
            "量子纠缠的贝尔不等式验证",
            "--structure",
            "tidy-table",
        )
        self.assertEqual("no-suitable-case", outcome["retrieval_status"])
        self.assertEqual([], outcome["matches"])
        self.assertTrue(outcome["constraint_only_candidates"])
        for candidate in outcome["constraint_only_candidates"]:
            self.assertEqual(0.0, candidate["relevance_score"])
            self.assertEqual("constraint-only", candidate["match_basis"])
            self.assertTrue(
                any(
                    reason["match_type"] == "explicit-hard-gate"
                    for reason in candidate["match_reasons"]
                )
            )

    def test_weak_query_evidence_cannot_bypass_threshold_with_a_constraint(self) -> None:
        outcome = run_ranker(
            "--query",
            "general",
            "--structure",
            "tidy-table",
        )
        self.assertEqual("no-suitable-case", outcome["retrieval_status"])
        self.assertEqual([], outcome["matches"])
        self.assertTrue(outcome["constraint_only_candidates"])
        for candidate in outcome["constraint_only_candidates"]:
            self.assertLess(candidate["relevance_score"], 3.0)
            self.assertEqual(
                "semantic-relevance-below-threshold",
                candidate["constraint_only_reason"],
            )
        output = run_text_ranker(
            "--query",
            "general",
            "--structure",
            "tidy-table",
        )
        self.assertIn("semantic relevance is below threshold", output)
        self.assertNotIn("semantic relevance is zero", output)

    def test_explicit_constraints_do_not_inflate_relevance(self) -> None:
        query = "survival with censoring, a risk table, and group comparison"
        unconstrained = run_ranker("--query", query)
        constrained = run_ranker(
            "--query",
            query,
            "--structure",
            "time-to-event",
            "--family",
            "time-and-process",
            "--domain",
            "clinical",
        )
        self.assertEqual("rf-0018", unconstrained["matches"][0]["id"])
        self.assertEqual("rf-0018", constrained["matches"][0]["id"])
        self.assertEqual(
            unconstrained["matches"][0]["relevance_score"],
            constrained["matches"][0]["relevance_score"],
        )
        hard_gate_axes = {
            reason["axis"]
            for reason in constrained["matches"][0]["match_reasons"]
            if reason["match_type"] == "explicit-hard-gate"
        }
        self.assertEqual(
            {"data_structure", "decision_family", "domain"},
            hard_gate_axes,
        )

    def test_geospatial_domain_never_returns_unrelated_cases(self) -> None:
        outcome = run_ranker("--domain", "geospatial")
        candidates = [
            *outcome["matches"],
            *outcome["repair_required_candidates"],
        ]
        self.assertEqual(["rf-0159"], [case["id"] for case in candidates])

    def test_chinese_spatial_difference_exposes_repair_required_case(self) -> None:
        outcome = run_ranker("--query", "省级发病率的空间差异")
        self.assertEqual("repair-required-only", outcome["retrieval_status"])
        self.assertEqual(
            ["rf-0159"],
            [case["id"] for case in outcome["repair_required_candidates"]],
        )

    def test_repair_only_outcome_is_distinct_from_no_suitable_case(self) -> None:
        outcome = run_ranker(
            "--query",
            "regional choropleth with a versioned boundary and spatial join",
            "--domain",
            "geospatial",
        )
        self.assertEqual("repair-required-only", outcome["retrieval_status"])
        self.assertFalse(outcome["no_suitable_case"])
        self.assertFalse(outcome["has_production_ready_match"])
        self.assertEqual([], outcome["matches"])
        candidate = outcome["repair_required_candidates"][0]
        self.assertEqual("rf-0159", candidate["id"])
        self.assertTrue(candidate["repair_gate"])
        self.assertEqual("references/cases-extensions.md", candidate["card"])
        self.assertEqual("assets/cases/rf-0159.webp", candidate["asset"])

    def test_negated_structure_is_not_a_positive_hard_gate(self) -> None:
        outcome = run_ranker(
            "--query",
            "This is not paired; show distributions and raw observations",
            "--include-conditional",
        )
        self.assertNotEqual("rf-0173", outcome["matches"][0]["id"])
        self.assertEqual("rf-0104", outcome["matches"][0]["id"])

    def test_explicit_structure_overrides_query_inference(self) -> None:
        outcome = run_ranker(
            "--query",
            "This is not paired; show distributions and raw observations",
            "--structure",
            "independent-groups",
            "--include-conditional",
        )
        self.assertEqual("matched", outcome["retrieval_status"])
        self.assertEqual("rf-0104", outcome["matches"][0]["id"])

    def test_swimmer_language_does_not_force_survival_case(self) -> None:
        outcome = run_ranker(
            "--query",
            "患者事件时间、随访区间、泳道图",
            "--include-conditional",
        )
        self.assertEqual("rf-0035", outcome["matches"][0]["id"])
        self.assertNotEqual("rf-0018", outcome["matches"][0]["id"])

    def test_semantic_relevance_precedes_readiness_bonus(self) -> None:
        outcome = run_ranker(
            "--query",
            "expression heatmap",
            "--include-conditional",
            "--limit",
            "1",
        )
        self.assertEqual("rf-0054", outcome["matches"][0]["id"])
        self.assertGreater(outcome["matches"][0]["relevance_score"], 4.0)

    def test_text_output_exposes_repair_candidates_beside_ready_matches(self) -> None:
        output = run_text_ranker("--query", "heatmap")
        self.assertIn("repair-required candidates", output)
        self.assertIn("rf-0054", output)


if __name__ == "__main__":
    unittest.main()
