#!/usr/bin/env python3
"""Lint a SciPlot Figure Contract without requiring third-party packages.

JSON is the dependency-free interchange format. YAML is supported only when
PyYAML is already installed. The CT-* identifiers in this module are contract
lint identifiers; they intentionally do not reuse the FC/DI/ST/AR identifiers
reserved for figure QA in ``references/qa.md``.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Optional, Union


SCHEMA = "sciplot.contract-lint/v1"
SKILL_ROOT = Path(__file__).resolve().parents[1]
VOCABULARY_PATH = SKILL_ROOT / "references" / "schema-vocabularies.json"
LEXICON_PATH = SKILL_ROOT / "references" / "retrieval-lexicon.json"
VOCABULARY = json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))
LEXICON = json.loads(LEXICON_PATH.read_text(encoding="utf-8"))
ENUMS = VOCABULARY["enums"]
ALLOWED_STAGES = set(ENUMS["validation_stage"])
ALLOWED_MODES = set(ENUMS["task_mode"])
ALLOWED_PHASES = set(ENUMS["task_phase"])
ALLOWED_PROFILES = set(ENUMS["contract_profile"])
ALLOWED_EXECUTION_STATES = set(ENUMS["execution_state"])
ALLOWED_CLAIM_LEVELS = set(ENUMS["claim_level"])
ALLOWED_CLAIM_STATUSES = set(ENUMS["claim_status"])
ALLOWED_EVIDENCE_ROLES = set(ENUMS["evidence_role"])
ALLOWED_DESTINATIONS = set(ENUMS["destination"])
ALLOWED_FORMATS = set(ENUMS["output_format"])
ALLOWED_REUSE = set(ENUMS["reuse_level"])
ALLOWED_RETRIEVAL_STATUSES = set(ENUMS["retrieval_status"])
ALLOWED_AUDIT_STATUSES = set(ENUMS["case_audit_status"])
ALLOWED_IMPLEMENTATION_STATUSES = set(ENUMS["case_implementation_status"])
ALLOWED_RISK_STATUSES = set(ENUMS["risk_status"])
SUPPORTED_CONTRACT_VERSIONS = set(ENUMS["contract_version"])
TRANSFORMATION_HINTS = tuple(LEXICON["transformation_hints"])
TRANSFORMATION_GUARD_TOKENS = tuple(LEXICON["transformation_guard_tokens"])
NOT_APPLICABLE_VALUES = {
    "n/a",
    "na",
    "none",
    "not applicable",
    "not-applicable",
}
INFERENTIAL_STATISTIC_MARKERS = {
    "confidence interval",
    "credible interval",
    "hypothesis test",
    "p value",
    "p-value",
    "p_value",
    "statistical significance",
    "t-test",
    "t test",
    "anova",
    "wilcoxon",
    "mann-whitney",
    "regression model",
    "cox model",
    "hazard ratio",
    "odds ratio",
}
PLACEHOLDER_PATTERNS = (
    re.compile(
        r"(?<![A-Za-z0-9_])(?:tbd|todo|fixme|placeholder)(?![A-Za-z0-9_])",
        re.I,
    ),
    re.compile(r"\?{3,}"),
    re.compile(r"(?:待补(?:充)?|待填(?:写)?|待确认|待定|待完善|稍后补充)"),
    re.compile(
        r"\b(?:to be determined|to be completed|to be filled|to be confirmed)\b",
        re.I,
    ),
)
CRITICAL_PLACEHOLDER_ROOTS = {
    "task",
    "question",
    "estimands",
    "claims",
    "evidence",
    "panels",
    "data_integrity",
    "traceability",
    "visual_system",
    "target",
    "implementation",
    "review_risks",
    "acceptance",
    "unknowns",
}
REQUIRED_ESTIMAND_FIELDS = (
    "population_or_system",
    "analysis_unit",
    "outcome",
    "timepoint_or_horizon",
    "contrast_or_exposure",
    "summary_measure",
    "effect_scale",
    "adjustment_or_aggregation",
    "missing_data_policy",
)
ESTIMAND_CLAIM_LEVELS = {
    "associational",
    "predictive",
    "causal",
}


def is_not_applicable_value(value: Any) -> bool:
    normalized = str(value).strip().lower()
    if normalized in NOT_APPLICABLE_VALUES:
        return True
    return any(
        normalized.startswith(prefix + separator)
        for prefix in ("not applicable", "not-applicable", "none", "n/a")
        for separator in (":", ";", ",", " — ", " - ", " because ")
    )


def load_contract(path: Path) -> dict[str, Any]:
    """Load a contract, preserving a dependency-free JSON path."""

    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
    else:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ValueError(
                "YAML validation requires PyYAML; use a JSON contract for the "
                "dependency-free path"
            ) from exc
        payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ValueError("contract root must be an object")
    return payload


def descriptive_statistics_conflicts(statistics: Any) -> list[str]:
    """Return inferential elements that contradict a descriptive task phase."""

    if isinstance(statistics, str):
        text = statistics.strip().lower()
        if is_not_applicable_value(text):
            return []
        return [
            marker
            for marker in sorted(INFERENTIAL_STATISTIC_MARKERS)
            if controlled_phrase_present(marker, text)
        ]
    if not isinstance(statistics, dict):
        return []

    conflicts: list[str] = []
    for field in ("test_or_model", "multiplicity"):
        value = statistics.get(field)
        if value is None:
            continue
        normalized = str(value).strip().lower()
        if normalized and not is_not_applicable_value(normalized):
            conflicts.append(field)
    semantic_statistics = {
        key: value
        for key, value in statistics.items()
        if not (
            key in {"test_or_model", "multiplicity"}
            and value is not None
            and is_not_applicable_value(value)
        )
    }
    serialized = json.dumps(semantic_statistics, ensure_ascii=False).lower()
    conflicts.extend(
        marker
        for marker in sorted(INFERENTIAL_STATISTIC_MARKERS)
        if controlled_phrase_present(marker, serialized)
    )
    return sorted(set(conflicts))


def get(payload: dict[str, Any], *path: str, default: Any = None) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def is_blank(value: Any) -> bool:
    return (
        value is None
        or value == ""
        or value == []
        or value == {}
        or (isinstance(value, str) and value.strip().lower() == "unknown")
    )


def contains_placeholder(value: Any) -> bool:
    """Return True only for explicit placeholder tokens, never short text."""

    return isinstance(value, str) and any(
        pattern.search(value) for pattern in PLACEHOLDER_PATTERNS
    )


def controlled_phrase_present(token: str, text: str) -> bool:
    """Match Latin terms by boundaries and CJK terms as normalized phrases."""

    token = unicodedata.normalize("NFKC", token).lower()
    text = unicodedata.normalize("NFKC", text).lower()
    token = re.sub(r"[-_/]+", " ", token)
    text = re.sub(r"[-_/]+", " ", text)
    token = re.sub(r"\s+", " ", token).strip()
    text = re.sub(r"\s+", " ", text).strip()
    if not token or not text:
        return False
    if re.search(r"[\u4e00-\u9fff]", token):
        return token in text
    return bool(
        re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", text)
    )


def iter_placeholder_paths(
    value: Any, path: tuple[Union[str, int], ...] = ()
) -> Iterable[tuple[Union[str, int], ...]]:
    """Yield paths whose scalar string values contain placeholder tokens."""

    if isinstance(value, dict):
        for key, child in value.items():
            yield from iter_placeholder_paths(child, path + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_placeholder_paths(child, path + (index,))
    elif contains_placeholder(value):
        yield path


def render_path(path: tuple[Union[str, int], ...]) -> str:
    """Render a nested JSON path in a compact, stable form."""

    rendered = ""
    for part in path:
        if isinstance(part, int):
            rendered += f"[{part}]"
        else:
            rendered += ("." if rendered else "") + part
    return rendered or "<root>"


def is_critical_placeholder_path(path: tuple[Union[str, int], ...]) -> bool:
    """Classify fields that affect scientific meaning or delivered artifacts."""

    return bool(path) and path[0] in CRITICAL_PLACEHOLDER_ROOTS


def is_explicit_text(value: Any) -> bool:
    """Return True for resolved audit prose without placeholder tokens."""

    return (
        isinstance(value, str)
        and not is_blank(value)
        and not contains_placeholder(value)
    )


def is_explicit_text_list(value: Any) -> bool:
    """Return True for a non-empty list of resolved audit statements."""

    return (
        isinstance(value, list)
        and bool(value)
        and all(is_explicit_text(item) for item in value)
    )


def is_traceable_support_basis(value: Any) -> bool:
    """Require each strong-claim support item to name a source and evidence."""

    return (
        isinstance(value, list)
        and bool(value)
        and all(
            isinstance(item, dict)
            and is_explicit_text(item.get("source"))
            and is_explicit_text(item.get("evidence"))
            for item in value
        )
    )


def is_count(value: Any) -> bool:
    """Return True for a finite, non-negative integer count (but not bool)."""

    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def is_positive_number(value: Any) -> bool:
    """Return True for a finite positive JSON number (but not bool)."""

    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def has_explicit_field_mapping(value: Any) -> bool:
    """Return True when a panel maps at least one named field."""

    return (
        isinstance(value, dict)
        and bool(value)
        and any(not is_blank(field) for field in value.values())
    )


def has_explicit_statistics(value: Any) -> bool:
    """Return True for stated statistics semantics or canonical non-applicability."""

    if isinstance(value, str):
        return value.strip().lower() == "not-applicable"
    return (
        isinstance(value, dict)
        and bool(value)
        and any(not is_blank(meaning) for meaning in value.values())
    )


def claim_requires_estimand(
    claim: Any,
    *,
    mode: Any,
    phase: Any,
    profile: Any,
) -> bool:
    """Return whether a production claim needs an explicit estimand ledger.

    The gate is deliberately narrow for contract-v1 compatibility: review,
    export, minimal, descriptive, exploratory, and presentation-only work can
    retain their existing contract shape. Publication confirmatory production
    routes must name the quantitative target for every non-descriptive claim.
    """

    return (
        isinstance(claim, dict)
        and mode in {"create", "adapt", "revise"}
        and phase == "confirmatory"
        and profile == "publication"
        and claim.get("level") in ESTIMAND_CLAIM_LEVELS
    )


def enum_message(path: str, allowed: Iterable[str]) -> str:
    return f"{path} must be one of {sorted(allowed)}"


def stage_status(stage: str, *, fail_from: str = "pre-render") -> str:
    """Return WARN until ``fail_from`` is reached, then FAIL."""

    order = {"plan": 0, "pre-render": 1, "final": 2}
    return "FAIL" if order[stage] >= order[fail_from] else "WARN"


def check_contract(
    payload: dict[str, Any], stage: str = "plan"
) -> list[dict[str, str]]:
    """Return stable, machine-readable CT-* lint results.

    ``plan`` permits documented incompleteness, ``pre-render`` blocks unknowns
    that could invalidate an artifact, and ``final`` additionally requires all
    review risks to be resolved or explicitly accepted.
    """

    if stage not in ALLOWED_STAGES:
        raise ValueError(enum_message("stage", ALLOWED_STAGES))

    checks: list[dict[str, str]] = []

    def add(check_id: str, status: str, message: str) -> None:
        checks.append({"id": check_id, "status": status, "message": message})

    # CT-001 — serialization contract and schema version.
    version = payload.get("contract_version")
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version not in SUPPORTED_CONTRACT_VERSIONS
    ):
        add(
            "CT-001",
            "FAIL",
            f"contract_version must be one of {sorted(SUPPORTED_CONTRACT_VERSIONS)}",
        )
    else:
        add("CT-001", "PASS", f"contract schema version {version}")

    # CT-002/003 — route and task vocabulary.
    task = payload.get("task")
    if not isinstance(task, dict):
        task = {}
        add("CT-002", "FAIL", "task must be an object")
    mode = task.get("mode")
    if mode not in ALLOWED_MODES:
        add("CT-002", "FAIL", enum_message("task.mode", ALLOWED_MODES))
    else:
        add("CT-002", "PASS", f"task route is {mode}")

    phase = task.get("phase")
    if phase not in ALLOWED_PHASES:
        add("CT-003", "FAIL", enum_message("task.phase", ALLOWED_PHASES))
    else:
        add("CT-003", "PASS", f"research phase is {phase}")

    # CT-004 — the phase must agree with claims and panel statistics. This is
    # intentionally conservative for descriptive work: it prevents a
    # confirmatory analysis from becoming "descriptive" by changing one enum.
    if phase == "descriptive":
        phase_conflicts: list[str] = []
        claims_for_phase = payload.get("claims", [])
        if isinstance(claims_for_phase, list):
            for index, claim in enumerate(claims_for_phase, start=1):
                if not isinstance(claim, dict):
                    continue
                level = claim.get("level")
                if level != "descriptive":
                    phase_conflicts.append(
                        f"claim {claim.get('id', index)} has level {level!r}"
                    )
        panels_for_phase = payload.get("panels", [])
        if isinstance(panels_for_phase, list):
            for index, panel in enumerate(panels_for_phase, start=1):
                if not isinstance(panel, dict):
                    continue
                conflicts = descriptive_statistics_conflicts(
                    panel.get("statistics")
                )
                if conflicts:
                    phase_conflicts.append(
                        f"panel {panel.get('id', index)} has inferential "
                        f"statistics {conflicts}"
                    )
        if phase_conflicts:
            add(
                "CT-004",
                "FAIL",
                "descriptive phase conflicts with: "
                + "; ".join(phase_conflicts),
            )
        else:
            add(
                "CT-004",
                "PASS",
                "descriptive phase contains no inferential claim or statistic",
            )

    profile = task.get("profile")
    if profile is None:
        add(
            "CT-003",
            stage_status(stage, fail_from="pre-render"),
            "task.profile is missing; select minimal, publication, or inferred-review",
        )
    elif profile not in ALLOWED_PROFILES:
        add("CT-003", "FAIL", enum_message("task.profile", ALLOWED_PROFILES))

    execution_state = task.get("execution_state")
    if execution_state is None:
        add(
            "CT-003",
            stage_status(stage, fail_from="pre-render"),
            "task.execution_state is missing",
        )
    elif execution_state not in ALLOWED_EXECUTION_STATES:
        add(
            "CT-003",
            "FAIL",
            enum_message("task.execution_state", ALLOWED_EXECUTION_STATES),
        )
    elif stage == "final" and execution_state != "proceed":
        add(
            "CT-003",
            "FAIL",
            "final validation requires task.execution_state=proceed",
        )
    elif stage == "pre-render" and execution_state == "blocked":
        add(
            "CT-003",
            "FAIL",
            "pre-render validation cannot run with task.execution_state=blocked",
        )

    # CT-010/011 — scientific question and claim ledger.
    question = get(payload, "question", "text")
    claims_value = payload.get("claims")
    if claims_value is None:
        claims: list[Any] = []
    elif isinstance(claims_value, list):
        claims = claims_value
    else:
        claims = []
        add("CT-011", "FAIL", "claims must be an array")

    if mode != "export" and is_blank(question) and not claims:
        add(
            "CT-010",
            "FAIL",
            "provide a scientific question or at least one bounded claim",
        )
    else:
        add("CT-010", "PASS", "question/claim gate is present or not applicable")

    claim_ids: list[str] = []
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            add("CT-011", "FAIL", f"claims[{index}] must be an object")
            continue
        claim_id = claim.get("id")
        if not isinstance(claim_id, str) or is_blank(claim_id):
            add("CT-011", "FAIL", f"claims[{index}].id must be a non-empty string")
        else:
            claim_ids.append(claim_id)
        if is_blank(claim.get("statement")):
            add("CT-011", "FAIL", f"claim {claim_id or index} has no statement")
        level = claim.get("level")
        if level not in ALLOWED_CLAIM_LEVELS:
            add(
                "CT-011",
                "FAIL",
                enum_message(f"claim {claim_id or index}.level", ALLOWED_CLAIM_LEVELS),
            )
        claim_status = claim.get("status")
        if claim_status not in ALLOWED_CLAIM_STATUSES:
            add(
                "CT-011",
                "FAIL",
                enum_message(
                    f"claim {claim_id or index}.status", ALLOWED_CLAIM_STATUSES
                ),
            )
    if len(claim_ids) != len(set(claim_ids)):
        add("CT-011", "FAIL", "claim IDs must be unique")
    elif claims and len(claim_ids) == len(claims):
        add("CT-011", "PASS", f"{len(claim_ids)} valid, unique claim IDs")
    elif not claims:
        add("CT-011", "PASS", "no claim ledger is required for this contract")
    known_claims = set(claim_ids)

    # Parse the estimand ledger before validating claims and panels that may
    # reference it. Estimands are an additive contract-v1 field: legacy
    # descriptive, minimal, review, export, and presentation contracts do not
    # need to add boilerplate merely to remain valid.
    estimands_value = payload.get("estimands")
    estimands: list[Any]
    estimand_structure_errors: list[str] = []
    if estimands_value is None:
        estimands = []
    elif isinstance(estimands_value, list):
        estimands = estimands_value
    else:
        estimands = []
        estimand_structure_errors.append("estimands must be an array")

    estimand_ids: list[str] = []
    estimand_missing_fields: dict[str, list[str]] = {}
    for index, estimand in enumerate(estimands):
        if not isinstance(estimand, dict):
            estimand_structure_errors.append(
                f"estimands[{index}] must be an object"
            )
            continue
        estimand_id = estimand.get("id")
        if not isinstance(estimand_id, str) or is_blank(estimand_id):
            estimand_structure_errors.append(
                f"estimands[{index}].id must be a non-empty string"
            )
            continue
        estimand_ids.append(estimand_id)
        missing = [
            field
            for field in REQUIRED_ESTIMAND_FIELDS
            if not is_explicit_text(estimand.get(field))
        ]
        if missing:
            estimand_missing_fields[estimand_id] = missing

    if len(estimand_ids) != len(set(estimand_ids)):
        estimand_structure_errors.append("estimand IDs must be unique")
    known_estimands = set(estimand_ids)

    claim_estimand_refs: dict[str, str] = {}
    required_claim_estimand_refs: dict[str, str] = {}
    required_estimand_gaps: list[str] = []
    required_estimand_ids: set[str] = set()
    optional_estimand_reference_gaps: list[str] = []
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue
        claim_label = str(claim.get("id") or index)
        estimand_id = claim.get("estimand_id")
        if estimand_id is not None:
            if not isinstance(estimand_id, str):
                estimand_structure_errors.append(
                    f"claim {claim_label}.estimand_id must be a non-empty string"
                )
            elif is_blank(estimand_id):
                optional_estimand_reference_gaps.append(
                    f"claim {claim_label}.estimand_id is unresolved"
                )
            elif estimand_id not in known_estimands:
                estimand_structure_errors.append(
                    f"claim {claim_label} references unknown estimand "
                    f"{estimand_id!r}"
                )
            else:
                claim_estimand_refs[claim_label] = estimand_id

        if claim_requires_estimand(
            claim,
            mode=mode,
            phase=phase,
            profile=profile,
        ):
            if not isinstance(estimand_id, str) or is_blank(estimand_id):
                required_estimand_gaps.append(
                    f"claim {claim_label} has no estimand_id"
                )
            elif estimand_id in known_estimands:
                required_estimand_ids.add(estimand_id)
                required_claim_estimand_refs[claim_label] = estimand_id
                missing = estimand_missing_fields.get(estimand_id, [])
                if missing:
                    required_estimand_gaps.append(
                        f"claim {claim_label} references incomplete estimand "
                        f"{estimand_id}: {', '.join(missing)}"
                    )

    # CT-015 — predictive and causal claims need claim-local, auditable
    # support. A control or diagnostic panel can contribute evidence, but its
    # mere presence is never a substitute for the design, support, assumptions,
    # and boundary records below.
    strong_claim_gaps: list[str] = []
    strong_claim_gap_statuses: list[str] = []
    strong_claim_count = 0
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict) or claim.get("level") not in {
            "predictive",
            "causal",
        }:
            continue
        strong_claim_count += 1
        claim_label = claim.get("id") or str(index)
        missing_or_invalid: list[str] = []
        if not is_explicit_text(claim.get("design_basis")):
            missing_or_invalid.append("design_basis")
        if not is_traceable_support_basis(claim.get("support_basis")):
            missing_or_invalid.append("support_basis")
        if not is_explicit_text_list(claim.get("assumptions")):
            missing_or_invalid.append("assumptions")
        if not is_explicit_text(claim.get("not_claimed")):
            missing_or_invalid.append("not_claimed")
        if missing_or_invalid:
            strong_claim_gap_statuses.append(str(claim.get("status")))
            strong_claim_gaps.append(
                f"claim {claim_label} lacks resolved "
                + ", ".join(missing_or_invalid)
            )

    if strong_claim_gaps:
        audit_only_route = mode in {"review", "export"}
        safely_unresolved = all(
            status in {"unknown", "not-supported"}
            for status in strong_claim_gap_statuses
        )
        severity = (
            "WARN"
            if audit_only_route and safely_unresolved
            else stage_status(stage)
        )
        route_note = (
            " Review/export may report this as unaudited only because every "
            "affected claim is marked unknown or not-supported; do not present "
            "the result as scientific validation."
            if audit_only_route and safely_unresolved
            else ""
        )
        add(
            "CT-015",
            severity,
            "predictive/causal claim audit is incomplete: "
            + "; ".join(strong_claim_gaps)
            + route_note,
        )
    elif strong_claim_count:
        add(
            "CT-015",
            "PASS",
            f"{strong_claim_count} predictive/causal claim(s) have auditable "
            "support and boundaries",
        )
    else:
        add("CT-015", "PASS", "no predictive or causal claim requires this gate")

    # CT-012/013 — panel ledger and panel-to-claim cross references.
    panels_value = payload.get("panels")
    if panels_value is None:
        panels: list[Any] = []
    elif isinstance(panels_value, list):
        panels = panels_value
    else:
        panels = []
        add("CT-012", "FAIL", "panels must be an array")

    panels_required = (
        profile == "publication"
        or (mode in {"create", "adapt"} and profile != "minimal")
        or (mode == "revise" and profile not in {"minimal", None})
    )
    if panels_required and not panels:
        add(
            "CT-012",
            stage_status(stage),
            "this route/profile requires a non-empty panel ledger",
        )

    panel_ids: list[str] = []
    panel_claim_links: dict[str, set[str]] = {}
    panel_estimand_refs: dict[str, str] = {}
    required_evidentiary_panel_estimand_gaps: list[str] = []
    for index, panel in enumerate(panels):
        if not isinstance(panel, dict):
            add("CT-012", "FAIL", f"panels[{index}] must be an object")
            continue
        panel_id = panel.get("id")
        if not isinstance(panel_id, str) or is_blank(panel_id):
            add("CT-012", "FAIL", f"panels[{index}].id must be a non-empty string")
            panel_label = str(index)
        else:
            panel_ids.append(panel_id)
            panel_label = panel_id

        role = panel.get("evidence_role")
        if role not in ALLOWED_EVIDENCE_ROLES:
            add(
                "CT-012",
                "FAIL",
                enum_message(
                    f"panel {panel_label}.evidence_role", ALLOWED_EVIDENCE_ROLES
                ),
            )

        required = (
            "question",
            "data_source",
            "analysis_unit",
            "unique_contribution",
        )
        missing = [name for name in required if is_blank(panel.get(name))]
        if profile == "publication":
            missing.extend(
                name
                for name in ("replicate_unit", "quantity_and_units")
                if is_blank(panel.get(name))
            )
            if not has_explicit_field_mapping(panel.get("fields")):
                missing.append("fields")
            if not has_explicit_statistics(panel.get("statistics")):
                missing.append("statistics")
        if missing:
            add(
                "CT-012",
                stage_status(stage),
                f"panel {panel_label} is missing {', '.join(missing)}",
            )

        supported = panel.get("supports_claims", [])
        if not isinstance(supported, list):
            add(
                "CT-013",
                "FAIL",
                f"panel {panel_label}.supports_claims must be an array",
            )
            supported = []
        bad_refs = [
            value
            for value in supported
            if not isinstance(value, str) or value not in known_claims
        ]
        if bad_refs:
            add(
                "CT-013",
                "FAIL",
                f"panel {panel_label} references unknown claims {bad_refs}",
            )
        if known_claims and not supported:
            add(
                "CT-013",
                stage_status(stage),
                f"panel {panel_label} supports no declared claim",
            )
        panel_claim_links[panel_label] = {
            value for value in supported if isinstance(value, str)
        }

        estimand_id = panel.get("estimand_id")
        linked_required_estimands = {
            required_claim_estimand_refs[claim_id]
            for claim_id in supported
            if claim_id in required_claim_estimand_refs
        }
        if role in {"primary", "supporting"} and linked_required_estimands and (
            not isinstance(estimand_id, str) or is_blank(estimand_id)
        ):
            required_evidentiary_panel_estimand_gaps.append(
                f"{role} panel {panel_label} must declare estimand_id "
                f"for publication confirmatory claim target(s) "
                f"{sorted(linked_required_estimands)}"
            )
        if estimand_id is not None:
            if not isinstance(estimand_id, str):
                estimand_structure_errors.append(
                    f"panel {panel_label}.estimand_id must be a non-empty string"
                )
            elif is_blank(estimand_id):
                optional_estimand_reference_gaps.append(
                    f"panel {panel_label}.estimand_id is unresolved"
                )
            elif estimand_id not in known_estimands:
                estimand_structure_errors.append(
                    f"panel {panel_label} references unknown estimand "
                    f"{estimand_id!r}"
                )
            else:
                panel_estimand_refs[panel_label] = estimand_id
                linked_estimands = {
                    claim_estimand_refs[claim_id]
                    for claim_id in supported
                    if claim_id in claim_estimand_refs
                }
                if linked_estimands and linked_estimands != {estimand_id}:
                    estimand_structure_errors.append(
                        f"panel {panel_label} estimand {estimand_id!r} conflicts "
                        f"with supported claim estimands {sorted(linked_estimands)}"
                    )

        statistics = panel.get("statistics")
        if isinstance(statistics, dict):
            if not is_blank(statistics.get("uncertainty")) and is_blank(
                statistics.get("n_definition")
            ):
                add(
                    "CT-012",
                    stage_status(stage),
                    f"panel {panel_label} has uncertainty but no n definition",
                )
            if not is_blank(statistics.get("test_or_model")) and is_blank(
                statistics.get("multiplicity")
            ):
                add(
                    "CT-012",
                    stage_status(stage),
                    f"panel {panel_label} has a test/model but no multiplicity statement",
                )

    if len(panel_ids) != len(set(panel_ids)):
        add("CT-012", "FAIL", "panel IDs must be unique")
    elif panels and len(panel_ids) == len(panels):
        add("CT-012", "PASS", f"{len(panel_ids)} valid, unique panel IDs")
    known_panels = set(panel_ids)

    # CT-016 — estimand ledger completeness and references. A malformed
    # reference is always a structural failure. Incompleteness becomes a
    # production failure only for the publication-confirmatory claims selected
    # by claim_requires_estimand(); optional ledgers remain advisory.
    if estimand_structure_errors:
        add(
            "CT-016",
            "FAIL",
            "estimand ledger/reference errors: "
            + "; ".join(estimand_structure_errors),
        )
    if required_estimand_gaps:
        add(
            "CT-016",
            stage_status(stage),
            "publication confirmatory claims require complete estimands: "
            + "; ".join(required_estimand_gaps),
        )
    if required_evidentiary_panel_estimand_gaps:
        add(
            "CT-016",
            stage_status(stage),
            "primary and supporting panels for publication confirmatory "
            "claims require the same explicit estimand_id: "
            + "; ".join(required_evidentiary_panel_estimand_gaps),
        )

    optional_incomplete = {
        estimand_id: missing
        for estimand_id, missing in estimand_missing_fields.items()
        if estimand_id not in required_estimand_ids
    }
    if optional_incomplete:
        rendered_gaps = "; ".join(
            f"{estimand_id}: {', '.join(missing)}"
            for estimand_id, missing in sorted(optional_incomplete.items())
        )
        add(
            "CT-016",
            "WARN",
            "optional estimand entries are incomplete: " + rendered_gaps,
        )
    if optional_estimand_reference_gaps:
        add(
            "CT-016",
            "WARN",
            "optional estimand references are unresolved: "
            + "; ".join(optional_estimand_reference_gaps),
        )
    if (
        not estimand_structure_errors
        and not required_estimand_gaps
        and not required_evidentiary_panel_estimand_gaps
        and not optional_incomplete
        and not optional_estimand_reference_gaps
    ):
        if estimands:
            add(
                "CT-016",
                "PASS",
                f"{len(estimand_ids)} complete, uniquely identified estimand(s)",
            )
        else:
            add(
                "CT-016",
                "PASS",
                "no estimand ledger is required by this route/profile/phase",
            )

    # CT-014 — traceability ledger and bidirectional reference integrity.
    traceability_value = payload.get("traceability")
    if traceability_value is None:
        traceability: list[Any] = []
    elif isinstance(traceability_value, list):
        traceability = traceability_value
    else:
        traceability = []
        add("CT-014", "FAIL", "traceability must be an array")

    traced_claims: set[str] = set()
    for index, item in enumerate(traceability):
        if not isinstance(item, dict):
            add("CT-014", "FAIL", f"traceability[{index}] must be an object")
            continue
        claim_id = item.get("claim_id")
        if claim_id not in known_claims:
            add(
                "CT-014",
                "FAIL",
                f"traceability[{index}] references unknown claim {claim_id!r}",
            )
        else:
            traced_claims.add(claim_id)
        supported_panels = item.get("supported_by_panels", [])
        if not isinstance(supported_panels, list) or not supported_panels:
            add(
                "CT-014",
                "FAIL",
                f"traceability for {claim_id!r} needs supported_by_panels",
            )
            continue
        bad_panels = [
            value
            for value in supported_panels
            if not isinstance(value, str) or value not in known_panels
        ]
        if bad_panels:
            add(
                "CT-014",
                "FAIL",
                f"traceability for {claim_id!r} references unknown panels {bad_panels}",
            )
        for panel_id in supported_panels:
            if (
                isinstance(panel_id, str)
                and panel_id in known_panels
                and isinstance(claim_id, str)
                and claim_id in known_claims
                and claim_id not in panel_claim_links.get(panel_id, set())
            ):
                add(
                    "CT-014",
                    "FAIL",
                    f"traceability links {claim_id} to panel {panel_id}, but the "
                    "panel does not declare that claim",
                )
    missing_trace = known_claims - traced_claims
    if missing_trace:
        add(
            "CT-014",
            stage_status(stage),
            f"claims lack traceability: {sorted(missing_trace)}",
        )
    elif known_claims:
        add("CT-014", "PASS", "all claims have valid panel traceability")

    # CT-020/021/022 — data-integrity and row/item reconciliation.
    integrity = payload.get("data_integrity")
    integrity_required = profile == "publication" or (
        mode in {"create", "adapt"} and profile != "minimal"
    )
    if not isinstance(integrity, dict):
        if integrity_required:
            add(
                "CT-020",
                stage_status(stage),
                "data_integrity is required for this route/profile",
            )
        else:
            add("CT-020", "PASS", "data_integrity is not required by this profile")
    else:
        add("CT-020", "PASS", "data_integrity block is present")
        expected = integrity.get("expected_rows_or_items")
        included = integrity.get("included_rows_or_items")
        unresolved_counts = is_blank(expected) or is_blank(included)
        if unresolved_counts:
            add(
                "CT-021",
                stage_status(stage),
                "expected_rows_or_items and included_rows_or_items must be resolved",
            )
        elif not is_count(expected) or not is_count(included):
            add("CT-021", "FAIL", "row/item counts must be non-negative integers")
        elif included > expected:
            add(
                "CT-021",
                "FAIL",
                f"included count {included} exceeds expected count {expected}",
            )
        else:
            add(
                "CT-021",
                "PASS",
                f"row/item counts are plausible ({expected} expected, {included} included)",
            )

        exclusions = integrity.get("exclusions", [])
        if not isinstance(exclusions, list):
            add("CT-022", "FAIL", "data_integrity.exclusions must be an array")
            exclusions = []

        previous_after: Optional[int] = None
        valid_exclusion_counts = True
        for index, exclusion in enumerate(exclusions):
            if not isinstance(exclusion, dict):
                add("CT-022", "FAIL", f"exclusions[{index}] must be an object")
                valid_exclusion_counts = False
                continue
            if is_blank(exclusion.get("predicate")) or is_blank(
                exclusion.get("reason")
            ):
                add(
                    "CT-022",
                    "FAIL",
                    f"exclusions[{index}] requires predicate and reason",
                )
            before = exclusion.get("before")
            after = exclusion.get("after")
            if not is_count(before) or not is_count(after):
                add(
                    "CT-022",
                    "FAIL",
                    f"exclusions[{index}] before/after must be non-negative integers",
                )
                valid_exclusion_counts = False
                continue
            if after > before:
                add(
                    "CT-022",
                    "FAIL",
                    f"exclusions[{index}] increases the count ({before} to {after})",
                )
                valid_exclusion_counts = False
            if previous_after is not None and before != previous_after:
                add(
                    "CT-022",
                    "FAIL",
                    f"exclusions[{index}] starts at {before}, expected {previous_after}",
                )
                valid_exclusion_counts = False
            previous_after = after

        if (
            exclusions
            and valid_exclusion_counts
            and is_count(expected)
            and is_count(included)
        ):
            first_before = exclusions[0].get("before")
            last_after = exclusions[-1].get("after")
            if first_before != expected or last_after != included:
                add(
                    "CT-022",
                    "FAIL",
                    "exclusion ledger does not reconcile expected and included counts",
                )
            else:
                add("CT-022", "PASS", "exclusion ledger reconciles")
        elif (
            not exclusions
            and is_count(expected)
            and is_count(included)
            and expected != included
        ):
            sampling = integrity.get("sampling")
            aggregation = integrity.get("aggregation")
            if is_blank(sampling) and is_blank(aggregation):
                add(
                    "CT-022",
                    stage_status(stage),
                    "count reduction has no exclusion, sampling, or aggregation record",
                )
            else:
                add(
                    "CT-022",
                    "WARN",
                    "count reduction relies on sampling/aggregation; verify its own counts",
                )
        elif not exclusions and not unresolved_counts:
            add("CT-022", "PASS", "no exclusion reconciliation is needed")

        transformations = integrity.get("transformations", [])
        serialized = json.dumps(transformations, ensure_ascii=False).lower()
        if any(
            controlled_phrase_present(token, serialized)
            for token in TRANSFORMATION_HINTS
        ) and not any(
            controlled_phrase_present(token, serialized)
            for token in TRANSFORMATION_GUARD_TOKENS
        ):
            add(
                "CT-023",
                stage_status(stage),
                "transformations appear to lack a definition-domain guard",
            )

    # CT-030 — delivery target and controlled output vocabulary.
    target = payload.get("target")
    target_required = profile == "publication" or mode == "export"
    if not isinstance(target, dict):
        if target_required:
            add(
                "CT-030",
                stage_status(stage),
                "target is required for this route/profile",
            )
    else:
        destination = target.get("destination")
        if destination not in ALLOWED_DESTINATIONS:
            add(
                "CT-030",
                "FAIL",
                enum_message("target.destination", ALLOWED_DESTINATIONS),
            )
        primary_format = target.get("primary_format")
        if primary_format not in ALLOWED_FORMATS:
            add(
                "CT-030",
                "FAIL",
                enum_message("target.primary_format", ALLOWED_FORMATS),
            )
        elif target_required and primary_format == "unknown":
            add(
                "CT-030",
                stage_status(stage),
                "target.primary_format must be resolved before rendering",
            )
        preview_format = target.get("preview_format")
        if preview_format is not None and preview_format not in ALLOWED_FORMATS:
            add(
                "CT-030",
                "FAIL",
                enum_message("target.preview_format", ALLOWED_FORMATS),
            )
        elif profile == "publication" and preview_format in {None, "unknown"}:
            add(
                "CT-030",
                stage_status(stage),
                "publication target.preview_format must be resolved before rendering",
            )
        elif mode == "export" and preview_format == "unknown":
            add(
                "CT-030",
                stage_status(stage),
                "explicit target.preview_format=unknown must be resolved before export",
            )

        declared_formats = target.get("formats")
        formats_for_checks: list[str] = []
        if declared_formats is None:
            # Preserve a compatibility path for older/minimal contracts, but
            # publication/export routes must explicitly declare every formal
            # deliverable rather than implying them from two role fields.
            formats_for_checks = [
                value
                for value in (primary_format, preview_format)
                if isinstance(value, str) and value != "unknown"
            ]
            if target_required:
                add(
                    "CT-030",
                    stage_status(stage),
                    "target.formats must explicitly list every formal deliverable",
                )
        elif not isinstance(declared_formats, list) or not declared_formats:
            add(
                "CT-030",
                "FAIL",
                "target.formats must be a non-empty list",
            )
        elif not all(isinstance(value, str) for value in declared_formats):
            add(
                "CT-030",
                "FAIL",
                "target.formats entries must be strings",
            )
        else:
            formats_for_checks = list(declared_formats)
            invalid_formats = sorted(set(formats_for_checks) - ALLOWED_FORMATS)
            if invalid_formats:
                add(
                    "CT-030",
                    "FAIL",
                    "target.formats contains unsupported values: "
                    + ", ".join(invalid_formats),
                )
            if len(formats_for_checks) != len(set(formats_for_checks)):
                add(
                    "CT-030",
                    "FAIL",
                    "target.formats must not contain duplicates",
                )
            if "unknown" in formats_for_checks:
                add(
                    "CT-030",
                    stage_status(stage),
                    "target.formats cannot contain unknown before rendering",
                )
            for field_name, role_format in (
                ("primary_format", primary_format),
                ("preview_format", preview_format),
            ):
                if (
                    isinstance(role_format, str)
                    and role_format != "unknown"
                    and role_format not in formats_for_checks
                ):
                    add(
                        "CT-030",
                        "FAIL",
                        f"target.{field_name} must also appear in target.formats",
                    )
        if target_required and is_blank(target.get("width_mm")):
            add(
                "CT-030",
                stage_status(stage),
                "target.width_mm must be resolved before rendering",
            )
        elif not is_blank(target.get("width_mm")) and (
            not isinstance(target.get("width_mm"), (int, float))
            or isinstance(target.get("width_mm"), bool)
            or target.get("width_mm") <= 0
        ):
            add("CT-030", "FAIL", "target.width_mm must be a positive number")
        if profile == "publication" and not any(
            is_positive_number(target.get(field))
            for field in ("height_mm", "height_mm_max")
        ):
            add(
                "CT-030",
                stage_status(stage),
                "publication target requires a positive height_mm or height_mm_max",
            )
        if any(
            output_format in {"png", "tiff"}
            for output_format in formats_for_checks
        ) and not is_positive_number(target.get("resolution_dpi")):
            add(
                "CT-030",
                stage_status(stage),
                "any PNG/TIFF formal deliverable requires a positive resolution_dpi",
            )

    # CT-031 — case-reuse vocabulary and backend-to-panel references.
    case_influence = get(payload, "implementation", "case_influence")
    if case_influence is not None:
        if not isinstance(case_influence, dict):
            add("CT-031", "FAIL", "implementation.case_influence must be an object")
        else:
            reuse = case_influence.get("reuse_level")
            if reuse is not None and reuse not in ALLOWED_REUSE:
                add("CT-031", "FAIL", enum_message("reuse_level", ALLOWED_REUSE))
            elif reuse is not None:
                add("CT-031", "PASS", f"reuse level is {reuse}")
            retrieval = case_influence.get("retrieval_status")
            if retrieval is not None and retrieval not in ALLOWED_RETRIEVAL_STATUSES:
                add(
                    "CT-031",
                    "FAIL",
                    enum_message("case_influence.retrieval_status", ALLOWED_RETRIEVAL_STATUSES),
                )
            audit_status = case_influence.get("audit_status_at_selection")
            if audit_status is not None and audit_status not in ALLOWED_AUDIT_STATUSES:
                add(
                    "CT-031",
                    "FAIL",
                    enum_message("case_influence.audit_status_at_selection", ALLOWED_AUDIT_STATUSES),
                )
            implementation_status = case_influence.get(
                "implementation_status_at_selection"
            )
            if (
                implementation_status is not None
                and implementation_status not in ALLOWED_IMPLEMENTATION_STATUSES
            ):
                add(
                    "CT-031",
                    "FAIL",
                    enum_message(
                        "case_influence.implementation_status_at_selection",
                        ALLOWED_IMPLEMENTATION_STATUSES,
                    ),
                )
            repair_satisfied = case_influence.get("repair_gate_satisfied")
            if repair_satisfied not in {None, True, False, "not-applicable"}:
                add(
                    "CT-031",
                    "FAIL",
                    "case_influence.repair_gate_satisfied must be true, false, or not-applicable",
                )
            if retrieval == "no-suitable-case" and reuse != "build-new":
                add(
                    "CT-031",
                    "FAIL",
                    "no-suitable-case requires reuse_level=build-new",
                )
            if (
                audit_status == "conditional"
                and repair_satisfied is not True
                and reuse in {"exact", "structural"}
            ):
                add(
                    "CT-031",
                    stage_status(stage),
                    "conditional case cannot be reused exactly or structurally until its repair gate is satisfied",
                )
            if implementation_status == "failed" and reuse in {"exact", "structural"}:
                add(
                    "CT-031",
                    "FAIL",
                    "failed implementation cannot be reused exactly or structurally",
                )

    backend_by_panel = get(payload, "implementation", "backend_by_panel")
    if backend_by_panel is not None:
        if not isinstance(backend_by_panel, dict):
            add("CT-031", "FAIL", "implementation.backend_by_panel must be an object")
        else:
            bad_backend_panels = sorted(set(backend_by_panel) - known_panels)
            if bad_backend_panels:
                add(
                    "CT-031",
                    "FAIL",
                    f"backend mapping references unknown panels {bad_backend_panels}",
                )

    # CT-040 — explicit unknowns and production blocking behavior.
    unknowns_value = payload.get("unknowns", [])
    if not isinstance(unknowns_value, list):
        unknowns: list[Any] = []
        add("CT-040", "FAIL", "unknowns must be an array")
    else:
        unknowns = unknowns_value

    blocking_unknowns: list[str] = []
    unresolved_nonblocking: list[str] = []
    for index, unknown in enumerate(unknowns):
        if not isinstance(unknown, dict):
            add("CT-040", "FAIL", f"unknowns[{index}] must be an object")
            continue
        field = unknown.get("field")
        consequence = unknown.get("consequence")
        blocking = unknown.get("blocking")
        if is_blank(field) or is_blank(consequence) or not isinstance(blocking, bool):
            add(
                "CT-040",
                "FAIL",
                f"unknowns[{index}] requires field, consequence, and boolean blocking",
            )
            continue
        if blocking:
            blocking_unknowns.append(str(field))
        else:
            unresolved_nonblocking.append(str(field))

    if blocking_unknowns:
        severity = stage_status(stage, fail_from="pre-render")
        if execution_state == "proceed":
            severity = "FAIL"
        add(
            "CT-040",
            severity,
            f"blocking unknowns remain: {blocking_unknowns}",
        )
    elif unknowns:
        add(
            "CT-040",
            "WARN" if stage == "final" else "PASS",
            f"only non-blocking unknowns remain: {unresolved_nonblocking}",
        )
    else:
        add("CT-040", "PASS", "no unresolved unknowns")

    # CT-041 — review-risk references and stage-specific closure.
    risks_value = payload.get("review_risks", [])
    if not isinstance(risks_value, list):
        risks: list[Any] = []
        add("CT-041", "FAIL", "review_risks must be an array")
    else:
        risks = risks_value

    open_risks: list[str] = []
    for index, risk in enumerate(risks):
        if not isinstance(risk, dict):
            add("CT-041", "FAIL", f"review_risks[{index}] must be an object")
            continue
        risk_name = risk.get("risk")
        risk_status = risk.get("status")
        if is_blank(risk_name):
            add("CT-041", "FAIL", f"review_risks[{index}].risk is required")
        if risk_status not in ALLOWED_RISK_STATUSES:
            add(
                "CT-041",
                "FAIL",
                enum_message(
                    f"review_risks[{index}].status", ALLOWED_RISK_STATUSES
                ),
            )
            continue
        affected = risk.get("affected_claims_or_panels", [])
        if not isinstance(affected, list):
            add(
                "CT-041",
                "FAIL",
                f"review_risks[{index}].affected_claims_or_panels must be an array",
            )
        else:
            known_refs = known_claims | known_panels
            bad_risk_refs = [
                value
                for value in affected
                if not isinstance(value, str) or value not in known_refs
            ]
            if bad_risk_refs:
                add(
                    "CT-041",
                    "FAIL",
                    f"review risk references unknown claims/panels {bad_risk_refs}",
                )
        if risk_status == "open":
            open_risks.append(str(risk_name or index))
            if stage in {"pre-render", "final"} and is_blank(risk.get("mitigation")):
                add(
                    "CT-041",
                    "FAIL",
                    f"open risk {risk_name or index!r} needs a mitigation before rendering",
                )

    if open_risks:
        add(
            "CT-041",
            "FAIL" if stage == "final" else "WARN",
            f"open review risks remain: {open_risks}",
        )
    elif risks:
        add("CT-041", "PASS", "all review risks are mitigated or accepted")
    else:
        add("CT-041", "PASS", "no review risks declared")

    # CT-042 — verifiable acceptance criteria.
    acceptance = payload.get("acceptance")
    acceptance_valid = (
        isinstance(acceptance, list)
        and bool(acceptance)
        and all(isinstance(item, str) and not is_blank(item) for item in acceptance)
    )
    if not acceptance_valid:
        add(
            "CT-042",
            stage_status(stage),
            "acceptance must be a non-empty array of verifiable criteria",
        )
    else:
        add("CT-042", "PASS", f"{len(acceptance)} acceptance criteria declared")

    # CT-043 — explicit placeholders are useful while planning, but must not
    # cross the production boundary in scientific or artifact-critical fields.
    placeholder_paths = list(iter_placeholder_paths(payload))
    if placeholder_paths:
        critical_paths = [
            render_path(path)
            for path in placeholder_paths
            if is_critical_placeholder_path(path)
        ]
        other_paths = [
            render_path(path)
            for path in placeholder_paths
            if not is_critical_placeholder_path(path)
        ]
        path_groups: list[str] = []
        if critical_paths:
            path_groups.append("critical=" + ", ".join(critical_paths))
        if other_paths:
            path_groups.append("other=" + ", ".join(other_paths))
        add(
            "CT-043",
            stage_status(stage) if critical_paths else "WARN",
            "explicit placeholder tokens remain: " + "; ".join(path_groups),
        )
    else:
        add("CT-043", "PASS", "no explicit placeholder tokens remain")

    return checks


def summarize(checks: list[dict[str, str]], stage: str) -> dict[str, Any]:
    statuses = {item["status"] for item in checks}
    status = "FAIL" if "FAIL" in statuses else "WARN" if "WARN" in statuses else "PASS"
    return {
        "schema": SCHEMA,
        "status": status,
        "stage": stage,
        "summary": {
            "pass": sum(item["status"] == "PASS" for item in checks),
            "warn": sum(item["status"] == "WARN" for item in checks),
            "fail": sum(item["status"] == "FAIL" for item in checks),
        },
        "checks": checks,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lint a SciPlot Figure Contract.")
    parser.add_argument("contract", type=Path)
    parser.add_argument(
        "--stage",
        choices=sorted(ALLOWED_STAGES),
        default="plan",
        help="Readiness gate to apply (default: plan).",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        payload = load_contract(args.contract)
        checks = check_contract(payload, stage=args.stage)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "status": "FAIL",
                    "stage": args.stage,
                    "error": str(exc),
                },
                ensure_ascii=False,
            )
        )
        return 2

    result = summarize(checks, stage=args.stage)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
