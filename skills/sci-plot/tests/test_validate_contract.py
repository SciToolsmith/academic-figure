"""Regression tests for the dependency-free Figure Contract linter."""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "scripts" / "validate_contract.py"
EXAMPLE_PATH = ROOT / "references" / "figure-contract.example.json"
DESCRIPTIVE_EXAMPLE_PATH = (
    ROOT / "references" / "figure-contract.descriptive-composition.example.json"
)
NATIVE_EXAMPLE_PATHS = {
    "raw-distribution-v1": (
        ROOT
        / "references"
        / "figure-contract.descriptive-distribution.example.json"
    ),
    "paired-change-v1": (
        ROOT / "references" / "figure-contract.descriptive-paired.example.json"
    ),
    "effect-forest-v1": (
        ROOT / "references" / "figure-contract.presentation-forest.example.json"
    ),
}

SPEC = importlib.util.spec_from_file_location("validate_contract", VALIDATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
validate_contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_contract)


def results_for(contract: dict, stage: str = "plan") -> list[dict[str, str]]:
    return validate_contract.check_contract(contract, stage=stage)


def statuses_for(
    contract: dict, check_id: str, stage: str = "plan"
) -> list[str]:
    return [
        item["status"]
        for item in results_for(contract, stage)
        if item["id"] == check_id
    ]


class FigureContractValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.example = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))

    def test_existing_example_passes_plan_gate(self) -> None:
        checks = results_for(self.example)
        self.assertNotIn("FAIL", {item["status"] for item in checks})
        self.assertIn(
            validate_contract.summarize(checks, "plan")["status"], {"PASS", "WARN"}
        )

    def test_examples_have_no_placeholder_or_strong_claim_gate_failure(self) -> None:
        examples = (
            self.example,
            json.loads(DESCRIPTIVE_EXAMPLE_PATH.read_text(encoding="utf-8")),
            *(
                json.loads(path.read_text(encoding="utf-8"))
                for path in NATIVE_EXAMPLE_PATHS.values()
            ),
        )
        for example in examples:
            for stage in ("plan", "pre-render", "final"):
                with self.subTest(phase=example["task"]["phase"], stage=stage):
                    self.assertEqual(statuses_for(example, "CT-015", stage), ["PASS"])
                    self.assertEqual(statuses_for(example, "CT-043", stage), ["PASS"])

    def test_native_examples_pass_final_gate_and_match_smoke_contracts(self) -> None:
        expected = {
            "raw-distribution-v1": ("descriptive", 18),
            "paired-change-v1": ("descriptive", 24),
            "effect-forest-v1": ("presentation", 6),
        }
        for native_id, path in NATIVE_EXAMPLE_PATHS.items():
            with self.subTest(native_id=native_id):
                contract = json.loads(path.read_text(encoding="utf-8"))
                phase, included = expected[native_id]
                native = contract["implementation"]["native_implementation"]
                self.assertEqual(native["id"], native_id)
                self.assertEqual(native["version"], "1.0.0")
                self.assertEqual(native["supported_task_phase"], phase)
                self.assertEqual(contract["task"]["phase"], phase)
                self.assertEqual(
                    contract["data_integrity"]["included_rows_or_items"],
                    included,
                )
                self.assertEqual(contract["target"]["width_mm"], 183)
                self.assertEqual(contract["target"]["height_mm"], 105)
                self.assertEqual(
                    contract["target"]["formats"],
                    ["svg", "pdf", "png"],
                )
                self.assertEqual(contract["target"]["primary_format"], "svg")
                self.assertEqual(contract["target"]["preview_format"], "png")
                self.assertEqual(contract["target"]["resolution_dpi"], 300)
                checks = results_for(contract, "final")
                self.assertEqual(
                    validate_contract.summarize(checks, "final")["status"],
                    "PASS",
                )

    def test_publication_confirmatory_claim_requires_complete_estimand(self) -> None:
        contract = copy.deepcopy(self.example)
        estimand = contract["estimands"][0]
        contract.pop("estimands")
        contract["claims"][0].pop("estimand_id")
        contract["panels"][0].pop("estimand_id")

        self.assertIn("WARN", statuses_for(contract, "CT-016", "plan"))
        self.assertIn("FAIL", statuses_for(contract, "CT-016", "pre-render"))
        self.assertIn("FAIL", statuses_for(contract, "CT-016", "final"))

        contract["estimands"] = [estimand]
        contract["claims"][0]["estimand_id"] = "E1"
        contract["panels"][0]["estimand_id"] = "E1"
        for stage in ("plan", "pre-render", "final"):
            self.assertEqual(statuses_for(contract, "CT-016", stage), ["PASS"])

    def test_required_estimand_fields_are_stage_gated(self) -> None:
        for field in validate_contract.REQUIRED_ESTIMAND_FIELDS:
            with self.subTest(field=field):
                contract = copy.deepcopy(self.example)
                del contract["estimands"][0][field]
                self.assertIn("WARN", statuses_for(contract, "CT-016", "plan"))
                self.assertIn(
                    "FAIL",
                    statuses_for(contract, "CT-016", "pre-render"),
                )
                self.assertIn("FAIL", statuses_for(contract, "CT-016", "final"))

    def test_estimand_references_must_resolve_and_panel_must_agree(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["claims"][0]["estimand_id"] = "E404"
        self.assertIn("FAIL", statuses_for(contract, "CT-016", "plan"))

        contract = copy.deepcopy(self.example)
        second = copy.deepcopy(contract["estimands"][0])
        second["id"] = "E2"
        contract["estimands"].append(second)
        contract["panels"][0]["estimand_id"] = "E2"
        self.assertIn("FAIL", statuses_for(contract, "CT-016", "plan"))

    def test_confirmatory_supporting_panel_requires_claim_estimand(self) -> None:
        contract = copy.deepcopy(self.example)
        supporting = copy.deepcopy(contract["panels"][0])
        supporting.update(
            {
                "id": "b",
                "evidence_role": "supporting",
                "question": "Does an independent supporting view bear on C1?",
                "unique_contribution": "adds a distinct supporting view of C1",
            }
        )
        supporting.pop("estimand_id")
        contract["panels"].append(supporting)
        contract["traceability"][0]["supported_by_panels"].append("b")

        self.assertIn("WARN", statuses_for(contract, "CT-016", "plan"))
        self.assertIn("FAIL", statuses_for(contract, "CT-016", "pre-render"))
        self.assertIn("FAIL", statuses_for(contract, "CT-016", "final"))

        contract["panels"][1]["estimand_id"] = "E1"
        for stage in ("plan", "pre-render", "final"):
            self.assertEqual(statuses_for(contract, "CT-016", stage), ["PASS"])

    def test_confirmatory_primary_panel_requires_claim_estimand(self) -> None:
        contract = copy.deepcopy(self.example)
        self.assertEqual(contract["panels"][0]["evidence_role"], "primary")
        contract["panels"][0].pop("estimand_id")

        self.assertIn("WARN", statuses_for(contract, "CT-016", "plan"))
        self.assertIn("FAIL", statuses_for(contract, "CT-016", "pre-render"))
        self.assertIn("FAIL", statuses_for(contract, "CT-016", "final"))

        contract["panels"][0]["estimand_id"] = "E1"
        for stage in ("plan", "pre-render", "final"):
            self.assertEqual(statuses_for(contract, "CT-016", stage), ["PASS"])

    def test_confirmatory_supporting_panel_rejects_conflicting_estimand(self) -> None:
        contract = copy.deepcopy(self.example)
        second = copy.deepcopy(contract["estimands"][0])
        second["id"] = "E2"
        contract["estimands"].append(second)
        supporting = copy.deepcopy(contract["panels"][0])
        supporting.update(
            {
                "id": "b",
                "estimand_id": "E2",
                "evidence_role": "supporting",
                "question": "Does a different target support C1?",
                "unique_contribution": "claims to support C1 using another target",
            }
        )
        contract["panels"].append(supporting)
        contract["traceability"][0]["supported_by_panels"].append("b")

        self.assertIn("FAIL", statuses_for(contract, "CT-016", "plan"))
        self.assertIn("FAIL", statuses_for(contract, "CT-016", "pre-render"))
        self.assertIn("FAIL", statuses_for(contract, "CT-016", "final"))

    def test_estimand_gate_does_not_block_exempt_routes_or_phases(self) -> None:
        scenarios = (
            ("create", "descriptive", "publication"),
            ("create", "presentation", "publication"),
            ("create", "confirmatory", "minimal"),
            ("review", "confirmatory", "inferred-review"),
            ("export", "confirmatory", "minimal"),
        )
        for mode, phase, profile in scenarios:
            with self.subTest(mode=mode, phase=phase, profile=profile):
                contract = copy.deepcopy(self.example)
                contract["task"].update(
                    {"mode": mode, "phase": phase, "profile": profile}
                )
                contract.pop("estimands")
                contract["claims"][0].pop("estimand_id")
                contract["panels"][0].pop("estimand_id")
                if phase == "descriptive":
                    contract["claims"][0]["level"] = "descriptive"
                    contract["panels"][0]["statistics"] = "not-applicable"
                self.assertNotIn(
                    "FAIL",
                    statuses_for(contract, "CT-016", "final"),
                )

    def test_optional_incomplete_estimand_warns_but_does_not_block(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["task"]["phase"] = "presentation"
        contract["estimands"][0].pop("missing_data_policy")
        self.assertEqual(statuses_for(contract, "CT-016", "final"), ["WARN"])

    def test_review_may_record_an_unresolved_estimand_reference(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["task"].update(
            {
                "mode": "review",
                "phase": "confirmatory",
                "profile": "inferred-review",
            }
        )
        contract["claims"][0]["estimand_id"] = "unknown"
        contract["panels"][0]["estimand_id"] = "unknown"
        contract["estimands"][0].pop("missing_data_policy")
        self.assertNotIn("FAIL", statuses_for(contract, "CT-016", "final"))
        self.assertIn("WARN", statuses_for(contract, "CT-016", "final"))

    def test_descriptive_statistics_do_not_match_p_value_inside_follow_up_values(
        self,
    ) -> None:
        contract = json.loads(
            NATIVE_EXAMPLE_PATHS["paired-change-v1"].read_text(encoding="utf-8")
        )
        self.assertEqual(statuses_for(contract, "CT-004", "final"), ["PASS"])

    def test_placeholders_warn_in_plan_and_block_critical_fields_later(self) -> None:
        placeholders = (
            "TBD",
            "TODO",
            "待补",
            "待填",
            "待定",
            "待完善",
            "placeholder",
            "???",
            "to be determined",
            "to be confirmed",
        )
        for marker in placeholders:
            with self.subTest(marker=marker):
                contract = copy.deepcopy(self.example)
                contract["question"]["text"] = f"Scientific question: {marker}"
                self.assertIn("WARN", statuses_for(contract, "CT-043", "plan"))
                self.assertIn(
                    "FAIL", statuses_for(contract, "CT-043", "pre-render")
                )
                self.assertIn("FAIL", statuses_for(contract, "CT-043", "final"))

    def test_short_scientific_terms_are_not_placeholders(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["question"]["text"] = "How do pH and BMI vary when n is eight?"
        contract["panels"][0]["fields"]["y"] = "pH"
        contract["panels"][0]["quantity_and_units"] = "pH"
        self.assertEqual(statuses_for(contract, "CT-043", "final"), ["PASS"])

    def test_control_or_diagnostic_panel_does_not_authorize_causal_claim(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["claims"][0]["level"] = "causal"
        contract["evidence"]["controls"] = ["negative control"]
        contract["evidence"]["diagnostics"] = ["model diagnostic"]
        contract["panels"][0]["evidence_role"] = "control"
        self.assertIn("WARN", statuses_for(contract, "CT-015", "plan"))
        self.assertIn("FAIL", statuses_for(contract, "CT-015", "pre-render"))
        self.assertIn("FAIL", statuses_for(contract, "CT-015", "final"))

    def test_predictive_claim_requires_structured_audit_fields(self) -> None:
        contract = copy.deepcopy(self.example)
        claim = contract["claims"][0]
        claim["level"] = "predictive"
        claim["design_basis"] = "Held-out temporal validation on a frozen cohort."
        claim["support_basis"] = "accuracy was high"
        claim["assumptions"] = []
        self.assertIn("WARN", statuses_for(contract, "CT-015", "plan"))
        self.assertIn("FAIL", statuses_for(contract, "CT-015", "pre-render"))

        claim["support_basis"] = [
            {"evidence": "AUROC on the frozen temporal holdout"}
        ]
        self.assertIn("FAIL", statuses_for(contract, "CT-015", "pre-render"))

        claim["support_basis"] = [
            {
                "source": "results/held-out-evaluation.json",
                "evidence": "AUROC on the frozen temporal holdout",
            }
        ]
        claim["assumptions"] = [
            "the target population follows the declared temporal deployment scope"
        ]
        claim["not_claimed"] = "Performance outside the declared deployment scope."
        for stage in ("plan", "pre-render", "final"):
            self.assertEqual(statuses_for(contract, "CT-015", stage), ["PASS"])

    def test_strong_claim_placeholder_is_not_resolved_audit_evidence(self) -> None:
        contract = copy.deepcopy(self.example)
        claim = contract["claims"][0]
        claim.update(
            {
                "level": "causal",
                "design_basis": "TBD",
                "support_basis": [
                    {"source": "TODO", "evidence": "placeholder"}
                ],
                "assumptions": ["待补"],
                "not_claimed": "???",
            }
        )
        self.assertIn("WARN", statuses_for(contract, "CT-015", "plan"))
        self.assertIn("FAIL", statuses_for(contract, "CT-015", "pre-render"))
        self.assertIn("FAIL", statuses_for(contract, "CT-043", "pre-render"))

    def test_review_and_export_can_report_an_unresolved_strong_claim(self) -> None:
        for mode, profile in (
            ("review", "inferred-review"),
            ("export", "minimal"),
        ):
            with self.subTest(mode=mode):
                contract = copy.deepcopy(self.example)
                contract["task"]["mode"] = mode
                contract["task"]["profile"] = profile
                claim = contract["claims"][0]
                claim["level"] = "causal"
                claim["status"] = "unknown"
                self.assertEqual(
                    statuses_for(contract, "CT-015", "final"),
                    ["WARN"],
                )

                claim["status"] = "supported"
                self.assertEqual(
                    statuses_for(contract, "CT-015", "final"),
                    ["FAIL"],
                )

    def test_localized_transformation_terms_require_a_domain_guard(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["data_integrity"]["transformations"] = ["对数变换"]
        self.assertIn("WARN", statuses_for(contract, "CT-023", "plan"))
        self.assertIn("FAIL", statuses_for(contract, "CT-023", "pre-render"))

        contract["data_integrity"]["transformations"] = [
            "对数变换；定义域严格为正，零值不进入变换"
        ]
        self.assertNotIn("FAIL", statuses_for(contract, "CT-023", "pre-render"))

    def test_transformation_terms_use_word_boundaries(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["data_integrity"]["transformations"] = [
            "instrument calibration only"
        ]
        self.assertNotIn("FAIL", statuses_for(contract, "CT-023", "pre-render"))

        contract["data_integrity"]["transformations"] = ["log2 transform"]
        self.assertIn("FAIL", statuses_for(contract, "CT-023", "pre-render"))

    def test_all_five_routes_are_supported(self) -> None:
        for mode in ("create", "adapt", "revise", "review", "export"):
            with self.subTest(mode=mode):
                contract = copy.deepcopy(self.example)
                contract["task"]["mode"] = mode
                self.assertNotIn("FAIL", statuses_for(contract, "CT-002"))

    def test_descriptive_phase_is_supported(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["task"]["phase"] = "descriptive"
        self.assertNotIn("FAIL", statuses_for(contract, "CT-003"))
        self.assertIn("FAIL", statuses_for(contract, "CT-004"))

    def test_descriptive_phase_rejects_inferential_statistics(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["task"]["phase"] = "descriptive"
        contract["claims"][0]["level"] = "descriptive"
        self.assertIn("FAIL", statuses_for(contract, "CT-004"))

        contract["panels"][0]["statistics"] = "not-applicable"
        self.assertNotIn("FAIL", statuses_for(contract, "CT-004"))

        contract["panels"][0]["statistics"] = {
            "center": "mean",
            "uncertainty": "standard deviation",
            "test_or_model": "not applicable because the claim is descriptive",
            "multiplicity": "none",
        }
        self.assertNotIn("FAIL", statuses_for(contract, "CT-004"))

    def test_invalid_enums_fail(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["task"]["phase"] = "speculative"
        contract["claims"][0]["level"] = "rhetorical"
        contract["panels"][0]["evidence_role"] = "decoration"
        checks = results_for(contract)
        self.assertIn("FAIL", statuses_for(contract, "CT-003"))
        self.assertIn("FAIL", statuses_for(contract, "CT-011"))
        self.assertIn("FAIL", statuses_for(contract, "CT-012"))
        self.assertEqual(validate_contract.summarize(checks, "plan")["status"], "FAIL")

    def test_contract_version_must_be_an_integer(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["contract_version"] = 1.0
        self.assertIn("FAIL", statuses_for(contract, "CT-001"))

    def test_bad_claim_and_panel_references_fail(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["panels"][0]["supports_claims"] = ["C404"]
        contract["traceability"][0]["supported_by_panels"] = ["z"]
        self.assertIn("FAIL", statuses_for(contract, "CT-013"))
        self.assertIn("FAIL", statuses_for(contract, "CT-014"))

    def test_blocking_unknown_warns_in_plan_and_fails_before_render(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["task"]["profile"] = "publication"
        contract["task"]["execution_state"] = "prototype-only"
        contract["unknowns"] = [
            {
                "field": "panels.a.analysis_unit",
                "consequence": "n and uncertainty cannot be interpreted",
                "blocking": True,
            }
        ]
        self.assertIn("WARN", statuses_for(contract, "CT-040", "plan"))
        self.assertIn("FAIL", statuses_for(contract, "CT-040", "pre-render"))
        self.assertIn("FAIL", statuses_for(contract, "CT-040", "final"))

    def test_proceed_contradicts_a_blocking_unknown_at_any_stage(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["task"]["execution_state"] = "proceed"
        contract["unknowns"] = [
            {
                "field": "data.mapping",
                "consequence": "values could map to the wrong quantity",
                "blocking": True,
            }
        ]
        self.assertIn("FAIL", statuses_for(contract, "CT-040", "plan"))

    def test_blocked_execution_state_cannot_enter_pre_render(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["task"]["execution_state"] = "blocked"
        self.assertNotIn("FAIL", statuses_for(contract, "CT-003", "plan"))
        self.assertIn("FAIL", statuses_for(contract, "CT-003", "pre-render"))

    def test_open_risk_warns_until_final_then_fails(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["task"]["profile"] = "publication"
        contract["task"]["execution_state"] = "proceed"
        contract["review_risks"] = [
            {
                "risk": "a label may overstate the available evidence",
                "affected_claims_or_panels": ["C1", "a"],
                "mitigation": "qualify the label before final delivery",
                "status": "open",
            }
        ]
        self.assertIn("WARN", statuses_for(contract, "CT-041", "plan"))
        self.assertIn("WARN", statuses_for(contract, "CT-041", "pre-render"))
        self.assertIn("FAIL", statuses_for(contract, "CT-041", "final"))

    def test_missing_acceptance_warns_in_plan_and_fails_before_render(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["acceptance"] = []
        self.assertIn("WARN", statuses_for(contract, "CT-042", "plan"))
        self.assertIn("FAIL", statuses_for(contract, "CT-042", "pre-render"))

    def test_row_ledger_must_reconcile(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["data_integrity"]["exclusions"][0]["after"] = 191
        self.assertIn("FAIL", statuses_for(contract, "CT-022"))

    def test_case_selection_enums_are_validated(self) -> None:
        contract = copy.deepcopy(self.example)
        influence = contract["implementation"]["case_influence"]
        influence["retrieval_status"] = "looks-close"
        influence["audit_status_at_selection"] = "pretty"
        influence["implementation_status_at_selection"] = "probably-runs"
        self.assertIn("FAIL", statuses_for(contract, "CT-031"))

    def test_no_suitable_case_requires_build_new(self) -> None:
        contract = copy.deepcopy(self.example)
        influence = contract["implementation"]["case_influence"]
        influence["retrieval_status"] = "no-suitable-case"
        influence["reuse_level"] = "structural"
        self.assertIn("FAIL", statuses_for(contract, "CT-031"))

    def test_conditional_case_needs_repair_before_structural_reuse(self) -> None:
        contract = copy.deepcopy(self.example)
        influence = contract["implementation"]["case_influence"]
        influence["audit_status_at_selection"] = "conditional"
        influence["repair_gate_satisfied"] = False
        influence["reuse_level"] = "structural"
        self.assertIn("WARN", statuses_for(contract, "CT-031", "plan"))
        self.assertIn("FAIL", statuses_for(contract, "CT-031", "pre-render"))

    def test_publication_panel_semantics_are_stage_gated(self) -> None:
        for field in (
            "replicate_unit",
            "fields",
            "quantity_and_units",
            "statistics",
        ):
            with self.subTest(field=field):
                contract = copy.deepcopy(self.example)
                del contract["panels"][0][field]
                self.assertIn("WARN", statuses_for(contract, "CT-012", "plan"))
                self.assertIn(
                    "FAIL", statuses_for(contract, "CT-012", "pre-render")
                )
                self.assertIn("FAIL", statuses_for(contract, "CT-012", "final"))

    def test_publication_panel_statistics_may_be_not_applicable(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["panels"][0]["statistics"] = "not-applicable"
        self.assertNotIn("WARN", statuses_for(contract, "CT-012", "plan"))
        self.assertNotIn("FAIL", statuses_for(contract, "CT-012", "pre-render"))
        self.assertNotIn("FAIL", statuses_for(contract, "CT-012", "final"))

    def test_publication_panel_statistics_must_be_explicit(self) -> None:
        for statistics in ({}, {"center": None}, "unknown"):
            with self.subTest(statistics=statistics):
                contract = copy.deepcopy(self.example)
                contract["panels"][0]["statistics"] = statistics
                self.assertIn("WARN", statuses_for(contract, "CT-012", "plan"))
                self.assertIn(
                    "FAIL", statuses_for(contract, "CT-012", "pre-render")
                )

    def test_publication_target_requires_a_positive_height_constraint(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["target"].pop("height_mm_max")
        self.assertIn("WARN", statuses_for(contract, "CT-030", "plan"))
        self.assertIn("FAIL", statuses_for(contract, "CT-030", "pre-render"))
        self.assertIn("FAIL", statuses_for(contract, "CT-030", "final"))

        contract["target"]["height_mm"] = 78
        self.assertNotIn("WARN", statuses_for(contract, "CT-030", "plan"))
        self.assertNotIn("FAIL", statuses_for(contract, "CT-030", "pre-render"))

    def test_publication_target_requires_explicit_formal_formats(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["target"].pop("formats")
        self.assertIn("WARN", statuses_for(contract, "CT-030", "plan"))
        self.assertIn("FAIL", statuses_for(contract, "CT-030", "pre-render"))
        self.assertIn("FAIL", statuses_for(contract, "CT-030", "final"))

    def test_format_roles_must_be_declared_as_formal_deliverables(self) -> None:
        contract = copy.deepcopy(self.example)
        contract["target"]["formats"] = ["svg", "pdf"]
        self.assertIn("FAIL", statuses_for(contract, "CT-030", "plan"))

    def test_publication_preview_role_must_be_resolved(self) -> None:
        for value in (None, "unknown"):
            with self.subTest(value=value):
                contract = copy.deepcopy(self.example)
                if value is None:
                    contract["target"].pop("preview_format")
                else:
                    contract["target"]["preview_format"] = value
                self.assertIn("WARN", statuses_for(contract, "CT-030", "plan"))
                self.assertIn(
                    "FAIL", statuses_for(contract, "CT-030", "pre-render")
                )

    def test_raster_target_requires_positive_dpi_after_plan(self) -> None:
        for raster_format in ("png", "tiff"):
            with self.subTest(raster_format=raster_format):
                contract = copy.deepcopy(self.example)
                contract["task"]["profile"] = "minimal"
                contract["target"]["formats"] = ["svg", raster_format]
                contract["target"]["preview_format"] = raster_format
                contract["target"]["resolution_dpi"] = 0
                self.assertIn("WARN", statuses_for(contract, "CT-030", "plan"))
                self.assertIn(
                    "FAIL", statuses_for(contract, "CT-030", "pre-render")
                )
                self.assertIn("FAIL", statuses_for(contract, "CT-030", "final"))

                contract["target"]["resolution_dpi"] = 300
                self.assertNotIn("WARN", statuses_for(contract, "CT-030", "plan"))
                self.assertNotIn(
                    "FAIL", statuses_for(contract, "CT-030", "pre-render")
                )


if __name__ == "__main__":
    unittest.main()
