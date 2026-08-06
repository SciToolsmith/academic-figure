#!/usr/bin/env python3
"""Merge SciPlot validator outputs into one stable QA report.

Inputs may be Figure Contract validator output, artifact-inspector output, or an
already normalized report. The tool never runs validators itself; it combines
their recorded evidence without turning a missing layer into an implicit PASS.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "sciplot.qa-report/v1"
VALID_STATUSES = {"PASS", "WARN", "FAIL"}
STATUS_ORDER = {"PASS": 0, "WARN": 1, "FAIL": 2}


def _status(checks: Iterable[dict[str, Any]]) -> str:
    worst = max((STATUS_ORDER.get(str(item.get("status")), 2) for item in checks), default=1)
    return ("PASS", "WARN", "FAIL")[worst]


def _load(path: Path) -> dict[str, Any]:
    if str(path) == "-":
        payload = json.load(sys.stdin)
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: report root must be an object")
    return payload


def _source_name(path: Path, payload: dict[str, Any]) -> str:
    schema = payload.get("schema")
    if isinstance(schema, str) and schema:
        return schema
    return "stdin" if str(path) == "-" else path.name


def _normalized_check(
    item: dict[str, Any],
    *,
    source: str,
    index: int,
) -> dict[str, Any]:
    raw_status = str(item.get("status", "FAIL")).upper()
    status = raw_status if raw_status in VALID_STATUSES else "FAIL"
    check_id = item.get("id")
    if not isinstance(check_id, str) or not check_id.strip():
        check_id = f"QA-INPUT-{index:03d}"
    evidence = item.get("evidence", item.get("message"))
    if not isinstance(evidence, str) or not evidence.strip():
        evidence = "source check did not provide textual evidence"
        status = "FAIL"
    result: dict[str, Any] = {
        "id": check_id,
        "status": status,
        "evidence": evidence,
        "source": source,
    }
    for key in ("artifact", "details", "phase", "blocking", "strict_promotion"):
        if key in item:
            result[key] = item[key]
    return result


def _normalized_unresolved(
    item: Any,
    *,
    source: str,
    index: int,
) -> dict[str, Any]:
    if isinstance(item, dict):
        result = dict(item)
    else:
        result = {"evidence": str(item)}
    raw_status = str(result.get("status", "")).upper()
    if raw_status in {"WARN", "FAIL"}:
        status = raw_status
    elif raw_status == "PASS" or not raw_status:
        status = "WARN"
    else:
        status = "FAIL"
    evidence = result.get("evidence", result.get("message"))
    if not isinstance(evidence, str) or not evidence.strip():
        evidence = "source unresolved item did not provide textual evidence"
        status = "FAIL"
    check_id = result.get("id")
    if not isinstance(check_id, str) or not check_id.strip():
        result["id"] = f"QA-UNRESOLVED-{index:03d}"
    result["status"] = status
    result["evidence"] = evidence
    result["source"] = source
    return result


def _unresolved_is_represented(
    item: dict[str, Any],
    source_checks: list[dict[str, Any]],
) -> bool:
    return any(
        check.get("id") == item.get("id")
        and check.get("artifact") == item.get("artifact")
        and check.get("evidence") == item.get("evidence")
        and STATUS_ORDER.get(str(check.get("status")), 2)
        >= STATUS_ORDER.get(str(item.get("status")), 2)
        for check in source_checks
    )


def _unresolved_check(item: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": item["id"],
        "status": item["status"],
        "evidence": item["evidence"],
        "source": item["source"],
        "unresolved_input": True,
    }
    for key in ("artifact", "details", "phase", "blocking", "strict_promotion"):
        if key in item:
            result[key] = item[key]
    return result


def _artifact_key(item: dict[str, Any]) -> str:
    path = item.get("path")
    if isinstance(path, str) and path:
        return path
    sha = item.get("sha256")
    if isinstance(sha, str) and sha:
        return f"sha256:{sha}"
    return json.dumps(item, ensure_ascii=False, sort_keys=True)


def merge_reports(
    reports: list[tuple[str, dict[str, Any]]],
    *,
    strict: bool = False,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    artifacts_by_key: dict[str, dict[str, Any]] = {}
    explicit_unresolved: list[dict[str, Any]] = []
    layers: list[dict[str, Any]] = []
    layer_check_ranges: list[tuple[int, int]] = []

    for source, payload in reports:
        source_checks = payload.get("checks")
        before = len(checks)
        if isinstance(source_checks, list):
            for index, item in enumerate(source_checks, start=1):
                if not isinstance(item, dict):
                    checks.append(
                        {
                            "id": f"QA-INPUT-{index:03d}",
                            "status": "FAIL",
                            "evidence": "source checks array contains a non-object item",
                            "source": source,
                        }
                    )
                    continue
                checks.append(_normalized_check(item, source=source, index=index))
        else:
            checks.append(
                {
                    "id": "QA-INPUT",
                    "status": "FAIL",
                    "evidence": "source report has no checks array",
                    "source": source,
                }
            )

        normalized_source_checks = checks[before:]
        source_unresolved = payload.get("unresolved", [])
        if isinstance(source_unresolved, list):
            for index, item in enumerate(source_unresolved, start=1):
                normalized = _normalized_unresolved(
                    item,
                    source=source,
                    index=index,
                )
                explicit_unresolved.append(normalized)
                if not _unresolved_is_represented(
                    normalized,
                    normalized_source_checks,
                ):
                    signal = _unresolved_check(normalized)
                    checks.append(signal)
                    normalized_source_checks.append(signal)
        elif "unresolved" in payload:
            checks.append(
                {
                    "id": "QA-INPUT",
                    "status": "FAIL",
                    "evidence": "source unresolved field must be an array",
                    "source": source,
                }
            )
            normalized_source_checks = checks[before:]

        declared_status = str(payload.get("status", "")).upper()
        observed_status = _status(
            normalized_source_checks
        )
        if declared_status in VALID_STATUSES and STATUS_ORDER[declared_status] > STATUS_ORDER[observed_status]:
            checks.append(
                {
                    "id": "QA-INPUT",
                    "status": declared_status,
                    "evidence": (
                        f"source declares {declared_status}, which is more severe than its "
                        "normalized checks"
                    ),
                    "source": source,
                }
            )
            observed_status = declared_status
        layers.append(
            {
                "source": source,
                "schema": payload.get("schema"),
                "declared_status": declared_status if declared_status in VALID_STATUSES else None,
                "observed_status": observed_status,
            }
        )
        layer_check_ranges.append((before, len(checks)))

        source_artifacts = payload.get("artifacts", [])
        if isinstance(source_artifacts, list):
            for artifact in source_artifacts:
                if isinstance(artifact, str):
                    normalized_artifact = {"path": artifact}
                elif isinstance(artifact, dict):
                    normalized_artifact = dict(artifact)
                else:
                    continue
                normalized_artifact.setdefault("sources", [])
                if source not in normalized_artifact["sources"]:
                    normalized_artifact["sources"].append(source)
                key = _artifact_key(normalized_artifact)
                if key in artifacts_by_key:
                    existing = artifacts_by_key[key]
                    for field, value in normalized_artifact.items():
                        if field == "sources":
                            existing.setdefault("sources", [])
                            existing["sources"].extend(
                                item for item in value if item not in existing["sources"]
                            )
                        elif field not in existing or existing[field] is None:
                            existing[field] = value
                else:
                    artifacts_by_key[key] = normalized_artifact

    if strict:
        for item in checks + explicit_unresolved:
            if item["status"] == "WARN":
                item["status"] = "FAIL"
                item["strict_promotion"] = True
        for layer, (start, end) in zip(layers, layer_check_ranges):
            layer["observed_status"] = _status(checks[start:end])

    derived_unresolved = [
        {
            "id": item["id"],
            "status": item["status"],
            "evidence": item["evidence"],
            "source": item["source"],
            **({"artifact": item["artifact"]} if "artifact" in item else {}),
        }
        for item in checks
        if item["status"] != "PASS"
    ]
    unresolved: list[dict[str, Any]] = []
    seen_unresolved: set[str] = set()
    for item in derived_unresolved + explicit_unresolved:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if key not in seen_unresolved:
            seen_unresolved.add(key)
            unresolved.append(item)

    artifacts = list(artifacts_by_key.values())
    hashes = {
        str(item.get("path", item.get("name", f"artifact-{index}"))): item["sha256"]
        for index, item in enumerate(artifacts, start=1)
        if isinstance(item.get("sha256"), str)
    }
    result_status = _status(checks + explicit_unresolved)
    return {
        "schema": SCHEMA,
        "status": result_status,
        "strict": strict,
        "summary": {
            "pass": sum(item["status"] == "PASS" for item in checks),
            "warn": sum(item["status"] == "WARN" for item in checks),
            "fail": sum(item["status"] == "FAIL" for item in checks),
            "layers": len(layers),
            "artifacts": len(artifacts),
        },
        "layers": layers,
        "checks": checks,
        "artifacts": artifacts,
        "hashes": hashes,
        "unresolved": unresolved,
    }


def _same_file_target(left: Path, right: Path) -> bool:
    try:
        if left.resolve(strict=False) == right.resolve(strict=False):
            return True
    except (OSError, RuntimeError):
        pass
    try:
        return left.samefile(right)
    except (OSError, ValueError):
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge contract/artifact validator JSON into sciplot.qa-report/v1."
    )
    parser.add_argument(
        "reports",
        nargs="+",
        type=Path,
        help="JSON report paths; use '-' for one report from stdin.",
    )
    parser.add_argument("--strict", action="store_true", help="Promote WARN checks to FAIL.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    parser.add_argument("--output", type=Path, help="Write JSON here instead of stdout.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if sum(str(path) == "-" for path in args.reports) > 1:
        print(json.dumps({"schema": SCHEMA, "status": "FAIL", "error": "stdin may appear once"}))
        return 2
    if args.output:
        conflict = next(
            (
                report
                for report in args.reports
                if str(report) != "-" and _same_file_target(args.output, report)
            ),
            None,
        )
        if conflict is not None:
            print(
                json.dumps(
                    {
                        "schema": SCHEMA,
                        "status": "FAIL",
                        "error": (
                            "--output must not refer to an input report: "
                            f"{conflict}"
                        ),
                    },
                    ensure_ascii=False,
                )
            )
            return 2
    loaded: list[tuple[str, dict[str, Any]]] = []
    try:
        for path in args.reports:
            payload = _load(path)
            loaded.append((_source_name(path, payload), payload))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "FAIL", "error": str(exc)}))
        return 2
    result = merge_reports(loaded, strict=args.strict)
    rendered = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.output:
        try:
            args.output.write_text(rendered + "\n", encoding="utf-8")
        except OSError as exc:
            print(json.dumps({"schema": SCHEMA, "status": "FAIL", "error": str(exc)}))
            return 2
    else:
        print(rendered)
    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
