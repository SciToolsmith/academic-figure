#!/usr/bin/env python3
"""Validate a JSON or YAML serialization of the Figure Contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ALLOWED_MODES = {"create", "revise", "review"}
ALLOWED_REUSE = {"exact", "structural", "style-only", "build-new"}


def load_contract(path: Path) -> dict[str, Any]:
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


def get(payload: dict[str, Any], *path: str, default: Any = None) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def is_blank(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {} or value == "unknown"


def check_contract(payload: dict[str, Any]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []

    def add(check_id: str, status: str, message: str) -> None:
        checks.append({"id": check_id, "status": status, "message": message})

    mode = get(payload, "task", "mode")
    if mode not in ALLOWED_MODES:
        add("FC-01", "FAIL", f"task.mode must be one of {sorted(ALLOWED_MODES)}")
    else:
        add("FC-01", "PASS", f"task route is {mode}")

    question = get(payload, "question", "text")
    claims = payload.get("claims")
    if is_blank(question) and (not isinstance(claims, list) or not claims):
        add("FC-02", "FAIL", "provide a scientific question or at least one bounded claim")
    else:
        add("FC-02", "PASS", "question/claim gate is present")

    if not isinstance(claims, list):
        claims = []
    claim_ids = [claim.get("id") for claim in claims if isinstance(claim, dict)]
    if any(is_blank(value) for value in claim_ids) or len(claim_ids) != len(set(claim_ids)):
        add("CE-01", "FAIL", "claim IDs must be present and unique")
    elif claims:
        add("CE-01", "PASS", f"{len(claim_ids)} unique claim IDs")
    else:
        add("CE-01", "WARN", "exploratory contract has no claim ledger")

    panels = payload.get("panels")
    if not isinstance(panels, list) or not panels:
        add("FC-03", "FAIL", "panels must be a non-empty array")
        panels = []
    panel_ids = [panel.get("id") for panel in panels if isinstance(panel, dict)]
    if any(is_blank(value) for value in panel_ids) or len(panel_ids) != len(set(panel_ids)):
        add("FC-03", "FAIL", "panel IDs must be present and unique")
    elif panels:
        add("FC-03", "PASS", f"{len(panel_ids)} unique panels")

    known_claims = set(claim_ids)
    for panel in panels:
        if not isinstance(panel, dict):
            add("FC-04", "FAIL", "every panel must be an object")
            continue
        panel_id = panel.get("id", "?")
        required = ("question", "evidence_role", "data_source", "analysis_unit", "unique_contribution")
        missing = [name for name in required if is_blank(panel.get(name))]
        if missing:
            add("FC-04", "FAIL", f"panel {panel_id} is missing {', '.join(missing)}")
        supported = panel.get("supports_claims", [])
        if known_claims and not supported:
            add("CE-02", "WARN", f"panel {panel_id} supports no declared claim")
        unknown_claims = [value for value in supported if value not in known_claims]
        if unknown_claims:
            add("CE-02", "FAIL", f"panel {panel_id} references unknown claims {unknown_claims}")

        statistics = panel.get("statistics")
        if isinstance(statistics, dict):
            if not is_blank(statistics.get("uncertainty")) and is_blank(statistics.get("n_definition")):
                add("ST-01", "WARN", f"panel {panel_id} has uncertainty but no n definition")
            if not is_blank(statistics.get("test_or_model")) and is_blank(statistics.get("multiplicity")):
                add("ST-03", "WARN", f"panel {panel_id} has a test/model but no multiplicity statement")

    integrity = payload.get("data_integrity")
    if not isinstance(integrity, dict):
        add("DI-01", "FAIL", "data_integrity block is required")
    else:
        expected = integrity.get("expected_rows_or_items")
        included = integrity.get("included_rows_or_items")
        if is_blank(expected) or is_blank(included):
            add("DI-01", "WARN", "row/item ledger is unresolved")
        else:
            add("DI-01", "PASS", "row/item ledger is present")
        transformations = integrity.get("transformations", [])
        serialized = json.dumps(transformations, ensure_ascii=False).lower()
        if ("log" in serialized or "sqrt" in serialized or "ratio" in serialized) and not any(
            token in serialized for token in ("guard", "domain", "positive", "nonnegative", "定义域")
        ):
            add("DI-03", "WARN", "transformations appear to lack a definition-domain guard")

    traceability = payload.get("traceability")
    if claims and not isinstance(traceability, list):
        add("CE-03", "FAIL", "claims require a traceability ledger")
    elif isinstance(traceability, list):
        traced = {
            item.get("claim_id")
            for item in traceability
            if isinstance(item, dict) and item.get("supported_by_panels")
        }
        missing_trace = known_claims - traced
        if missing_trace:
            add("CE-03", "FAIL", f"claims lack traceability: {sorted(missing_trace)}")
        else:
            add("CE-03", "PASS", "all claims have panel traceability")

    target = payload.get("target")
    if not isinstance(target, dict):
        add("AR-01", "FAIL", "target block is required")
    else:
        if is_blank(target.get("width_mm")):
            add("AR-01", "WARN", "target physical width is unresolved")
        if is_blank(target.get("primary_format")):
            add("AR-01", "WARN", "primary output format is unresolved")

    reuse = get(payload, "implementation", "case_influence", "reuse_level")
    if reuse not in ALLOWED_REUSE:
        add("PR-01", "FAIL", f"reuse level must be one of {sorted(ALLOWED_REUSE)}")
    else:
        add("PR-01", "PASS", f"reuse level is {reuse}")

    risks = payload.get("review_risks")
    if not isinstance(risks, list):
        add("FC-05", "WARN", "review_risks should be an array, even when empty")

    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a Figure Contract.")
    parser.add_argument("contract", type=Path)
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        payload = load_contract(args.contract)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 2

    checks = check_contract(payload)
    statuses = {item["status"] for item in checks}
    status = "FAIL" if "FAIL" in statuses else "WARN" if "WARN" in statuses else "PASS"
    result = {
        "status": status,
        "summary": {
            "pass": sum(item["status"] == "PASS" for item in checks),
            "warn": sum(item["status"] == "WARN" for item in checks),
            "fail": sum(item["status"] == "FAIL" for item in checks),
        },
        "checks": checks,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 1 if status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
