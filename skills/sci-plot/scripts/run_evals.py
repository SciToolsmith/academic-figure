#!/usr/bin/env python3
"""Run deterministic SciPlot probes or validate external behavioral results.

This program deliberately does not call a model. Deterministic mode executes
only an allowlist of repository-local, read-only helpers. Behavioral mode
checks a separately produced result package against all catalog prompts and
expected assertions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = SKILL_ROOT / "evals" / "evals.json"
CATALOG_SCHEMA = "sciplot.eval-catalog/v2"
BEHAVIORAL_RESULTS_SCHEMA = "sciplot.behavioral-results/v1"
REPORT_SCHEMA = "sciplot.eval-report/v1"
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
READ_ONLY_PROBE_SCRIPTS = {
    "scripts/check_vocab_drift.py",
    "scripts/rank_cases.py",
    "scripts/validate_contract.py",
    "scripts/validate_implementations.py",
}
PATH_OVERRIDE_OPTIONS = {
    "--case-index",
    "--implementation-index",
    "--index",
    "--lexicon",
    "--vocabulary",
}
BEHAVIORAL_STATUSES = {"pass", "fail", "not-assessed"}
MISSING = object()


class EvalInputError(ValueError):
    """Raised when an eval catalog or result package is structurally unsafe."""


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EvalInputError(f"cannot read {label}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise EvalInputError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise EvalInputError(f"{label} must be a JSON object")
    return payload


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise EvalInputError(f"cannot hash eval catalog: {exc}") from exc
    return digest.hexdigest()


def is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_unfilled_template_value(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    return normalized.startswith(("replace-with-", "replace with "))


def validate_id(value: Any, label: str) -> str:
    if not is_nonempty_string(value) or not ID_PATTERN.fullmatch(value):
        raise EvalInputError(
            f"{label} must use lowercase letters, digits, and internal hyphens"
        )
    return value


def assertion_id(position: int) -> str:
    """Return the stable, catalog-order ID for one behavioral expectation."""

    return f"expected-{position:02d}"


def safe_probe_script(value: Any) -> tuple[str, Path]:
    if not is_nonempty_string(value):
        raise EvalInputError("deterministic probe script must be a non-empty string")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise EvalInputError(f"probe script escapes the skill root: {value!r}")
    normalized = relative.as_posix()
    if normalized not in READ_ONLY_PROBE_SCRIPTS:
        raise EvalInputError(
            f"probe script is not in the read-only allowlist: {normalized!r}"
        )
    resolved = (SKILL_ROOT / relative).resolve()
    try:
        resolved.relative_to((SKILL_ROOT / "scripts").resolve())
    except ValueError as exc:
        raise EvalInputError(
            f"probe script escapes the scripts directory: {value!r}"
        ) from exc
    if not resolved.is_file():
        raise EvalInputError(f"probe script does not exist: {normalized!r}")
    return normalized, resolved


def safe_skill_input(value: str, label: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise EvalInputError(f"{label} escapes the skill root: {value!r}")
    resolved = (SKILL_ROOT / relative).resolve()
    try:
        resolved.relative_to(SKILL_ROOT.resolve())
    except ValueError as exc:
        raise EvalInputError(
            f"{label} resolves outside the skill root: {value!r}"
        ) from exc
    if not resolved.is_file():
        raise EvalInputError(f"{label} does not exist: {value!r}")
    return resolved


def validate_pointer(pointer: Any, label: str) -> str:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise EvalInputError(f"{label} must be a JSON Pointer starting with '/'")
    for token in pointer.split("/")[1:]:
        if re.search(r"~(?![01])", token):
            raise EvalInputError(f"{label} contains an invalid JSON Pointer escape")
    return pointer


def validate_catalog(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema") != CATALOG_SCHEMA:
        raise EvalInputError(f"eval catalog must use {CATALOG_SCHEMA}")
    if payload.get("catalog_version") != 2:
        raise EvalInputError("eval catalog catalog_version must be 2")
    if payload.get("skill_name") != "sci-plot":
        raise EvalInputError("eval catalog skill_name must be sci-plot")

    boundary = payload.get("evaluation_boundary")
    if not isinstance(boundary, dict):
        raise EvalInputError("evaluation_boundary must be an object")
    if boundary.get("runner_invokes_external_agent") is not False:
        raise EvalInputError(
            "evaluation_boundary.runner_invokes_external_agent must be false"
        )
    for key in ("deterministic", "behavioral"):
        if not is_nonempty_string(boundary.get(key)):
            raise EvalInputError(f"evaluation_boundary.{key} is required")

    expected_protocol = {
        "runner": "scripts/run_evals.py",
        "behavioral_results_schema": BEHAVIORAL_RESULTS_SCHEMA,
        "report_schema": REPORT_SCHEMA,
        "expected_assertion_id_template": "expected-{position:02d}",
    }
    if payload.get("protocol") != expected_protocol:
        raise EvalInputError(
            "eval catalog protocol metadata does not match this runner"
        )

    probes = payload.get("deterministic_probes")
    if not isinstance(probes, list) or not probes:
        raise EvalInputError("deterministic_probes must be a non-empty array")
    seen_probe_ids: set[str] = set()
    for probe_position, probe in enumerate(probes, start=1):
        label = f"deterministic_probes[{probe_position - 1}]"
        if not isinstance(probe, dict):
            raise EvalInputError(f"{label} must be an object")
        probe_id = validate_id(probe.get("id"), f"{label}.id")
        if probe_id in seen_probe_ids:
            raise EvalInputError(f"duplicate deterministic probe id: {probe_id}")
        seen_probe_ids.add(probe_id)
        if not is_nonempty_string(probe.get("description")):
            raise EvalInputError(f"{label}.description is required")
        script_name, _ = safe_probe_script(probe.get("script"))
        arguments = probe.get("args")
        if not isinstance(arguments, list) or not all(
            isinstance(argument, str) and "\x00" not in argument
            for argument in arguments
        ):
            raise EvalInputError(f"{label}.args must be an array of safe strings")
        for argument in arguments:
            candidate = Path(argument)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise EvalInputError(
                    f"{label}.args contains an unsafe path-like value: {argument!r}"
                )
            option = argument.split("=", 1)[0]
            if option in PATH_OVERRIDE_OPTIONS:
                raise EvalInputError(
                    f"{label}.args may not override repository input paths: "
                    f"{option!r}"
                )
        if script_name == "scripts/validate_contract.py":
            if not arguments or arguments[0].startswith("-"):
                raise EvalInputError(
                    f"{label}.args must begin with a skill-relative contract path"
                )
            safe_skill_input(arguments[0], f"{label}.contract")
        expected_exit = probe.get("expected_exit")
        if (
            not isinstance(expected_exit, int)
            or isinstance(expected_exit, bool)
            or not 0 <= expected_exit <= 255
        ):
            raise EvalInputError(f"{label}.expected_exit must be an integer 0..255")
        assertions = probe.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            raise EvalInputError(f"{label}.assertions must be a non-empty array")
        seen_assertion_ids: set[str] = set()
        for assertion_position, assertion in enumerate(assertions, start=1):
            assertion_label = (
                f"{label}.assertions[{assertion_position - 1}]"
            )
            if not isinstance(assertion, dict):
                raise EvalInputError(f"{assertion_label} must be an object")
            item_id = validate_id(
                assertion.get("id"), f"{assertion_label}.id"
            )
            if item_id in seen_assertion_ids:
                raise EvalInputError(
                    f"{probe_id}: duplicate assertion id {item_id!r}"
                )
            seen_assertion_ids.add(item_id)
            validate_pointer(
                assertion.get("pointer"), f"{assertion_label}.pointer"
            )
            if assertion.get("operator") != "equals":
                raise EvalInputError(
                    f"{assertion_label}.operator must be 'equals'"
                )
            if "expected" not in assertion:
                raise EvalInputError(f"{assertion_label}.expected is required")

    evals = payload.get("evals")
    if not isinstance(evals, list) or len(evals) != 15:
        raise EvalInputError("evals must contain exactly 15 behavioral evals")
    seen_eval_ids: set[str] = set()
    for eval_position, item in enumerate(evals, start=1):
        label = f"evals[{eval_position - 1}]"
        if not isinstance(item, dict):
            raise EvalInputError(f"{label} must be an object")
        eval_id = validate_id(item.get("id"), f"{label}.id")
        if eval_id in seen_eval_ids:
            raise EvalInputError(f"duplicate behavioral eval id: {eval_id}")
        seen_eval_ids.add(eval_id)
        if not is_nonempty_string(item.get("prompt")):
            raise EvalInputError(f"{label}.prompt is required")
        expected = item.get("expected")
        if not isinstance(expected, list) or not expected or not all(
            is_nonempty_string(expectation) for expectation in expected
        ):
            raise EvalInputError(
                f"{label}.expected must be a non-empty string array"
            )
        if len(expected) != len(set(expected)):
            raise EvalInputError(f"{label}.expected contains duplicate assertions")
    return payload


def resolve_pointer(payload: Any, pointer: str) -> Any:
    current = payload
    for raw_token in pointer.split("/")[1:]:
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                return MISSING
            current = current[token]
        elif isinstance(current, list):
            if not token.isdigit():
                return MISSING
            position = int(token)
            if position >= len(current):
                return MISSING
            current = current[position]
        else:
            return MISSING
    return current


def json_value(value: Any) -> Any:
    return {"missing": True} if value is MISSING else value


def run_deterministic(
    catalog: dict[str, Any], catalog_path: Path
) -> dict[str, Any]:
    probe_reports: list[dict[str, Any]] = []
    assertion_pass = 0
    assertion_fail = 0
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        }
    )

    for probe in catalog["deterministic_probes"]:
        script_name, script_path = safe_probe_script(probe["script"])
        started = time.monotonic()
        stdout = ""
        stderr = ""
        returncode: Optional[int] = None
        execution_error: Optional[str] = None
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    str(script_path),
                    *probe["args"],
                ],
                cwd=SKILL_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            returncode = completed.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            execution_error = str(exc)

        exit_ok = returncode == probe["expected_exit"]
        parsed: Any = MISSING
        parse_error: Optional[str] = None
        if execution_error is None:
            try:
                parsed = json.loads(stdout)
            except json.JSONDecodeError as exc:
                parse_error = str(exc)

        checks: list[dict[str, Any]] = []
        for assertion in probe["assertions"]:
            observed = (
                resolve_pointer(parsed, assertion["pointer"])
                if parsed is not MISSING
                else MISSING
            )
            passed = observed is not MISSING and observed == assertion["expected"]
            assertion_pass += int(passed)
            assertion_fail += int(not passed)
            checks.append(
                {
                    "id": assertion["id"],
                    "status": "PASS" if passed else "FAIL",
                    "pointer": assertion["pointer"],
                    "operator": assertion["operator"],
                    "expected": assertion["expected"],
                    "observed": json_value(observed),
                }
            )

        probe_passed = (
            execution_error is None
            and parse_error is None
            and exit_ok
            and all(check["status"] == "PASS" for check in checks)
        )
        report: dict[str, Any] = {
            "id": probe["id"],
            "status": "PASS" if probe_passed else "FAIL",
            "script": script_name,
            "args": probe["args"],
            "expected_exit": probe["expected_exit"],
            "observed_exit": returncode,
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "assertions": checks,
        }
        if execution_error:
            report["execution_error"] = execution_error
        if parse_error:
            report["json_parse_error"] = parse_error
        if not probe_passed and stdout:
            report["stdout_excerpt"] = stdout[-4000:]
        if not probe_passed and stderr:
            report["stderr_excerpt"] = stderr[-4000:]
        probe_reports.append(report)

    passed_probes = sum(item["status"] == "PASS" for item in probe_reports)
    failed_probes = len(probe_reports) - passed_probes
    return {
        "schema": REPORT_SCHEMA,
        "mode": "deterministic",
        "status": "PASS" if failed_probes == 0 else "FAIL",
        "assessment_basis": "direct-repository-probes",
        "external_agent_invoked_by_runner": False,
        "catalog_sha256": file_sha256(catalog_path),
        "summary": {
            "probes_total": len(probe_reports),
            "probes_pass": passed_probes,
            "probes_fail": failed_probes,
            "assertions_pass": assertion_pass,
            "assertions_fail": assertion_fail,
        },
        "probes": probe_reports,
    }


def expected_assertions(item: dict[str, Any]) -> dict[str, str]:
    return {
        assertion_id(position): description
        for position, description in enumerate(item["expected"], start=1)
    }


def behavioral_template(
    catalog: dict[str, Any], catalog_path: Path
) -> dict[str, Any]:
    return {
        "schema": BEHAVIORAL_RESULTS_SCHEMA,
        "skill_name": catalog["skill_name"],
        "catalog_sha256": file_sha256(catalog_path),
        "run_id": "replace-with-external-run-id",
        "producer": {
            "kind": "external-agent",
            "name": "replace-with-agent-or-evaluator-name",
        },
        "results": [
            {
                "eval_id": item["id"],
                "response": "",
                "assertions": [
                    {
                        "assertion_id": item_id,
                        "status": "not-assessed",
                        "evidence": "replace with result-specific evidence",
                    }
                    for item_id in expected_assertions(item)
                ],
            }
            for item in catalog["evals"]
        ],
    }


def validate_behavioral_header(
    payload: dict[str, Any],
    catalog: dict[str, Any],
    catalog_path: Path,
) -> None:
    if payload.get("schema") != BEHAVIORAL_RESULTS_SCHEMA:
        raise EvalInputError(
            f"behavioral results must use {BEHAVIORAL_RESULTS_SCHEMA}"
        )
    if payload.get("skill_name") != catalog["skill_name"]:
        raise EvalInputError("behavioral results skill_name does not match catalog")
    expected_digest = file_sha256(catalog_path)
    if payload.get("catalog_sha256") != expected_digest:
        raise EvalInputError(
            "behavioral results catalog_sha256 does not match the exact catalog"
        )
    if not is_nonempty_string(payload.get("run_id")) or is_unfilled_template_value(
        payload.get("run_id")
    ):
        raise EvalInputError("behavioral results run_id is required")
    producer = payload.get("producer")
    if not isinstance(producer, dict):
        raise EvalInputError("behavioral results producer must be an object")
    if producer.get("kind") != "external-agent":
        raise EvalInputError(
            "behavioral results producer.kind must be external-agent"
        )
    if not is_nonempty_string(producer.get("name")) or is_unfilled_template_value(
        producer.get("name")
    ):
        raise EvalInputError("behavioral results producer.name is required")
    if not isinstance(payload.get("results"), list):
        raise EvalInputError("behavioral results results must be an array")


def validate_behavioral_results(
    payload: dict[str, Any],
    catalog: dict[str, Any],
    catalog_path: Path,
) -> dict[str, Any]:
    validate_behavioral_header(payload, catalog, catalog_path)
    catalog_by_id = {item["id"]: item for item in catalog["evals"]}
    received: dict[str, dict[str, Any]] = {}
    package_errors: list[str] = []

    for position, result in enumerate(payload["results"]):
        label = f"results[{position}]"
        if not isinstance(result, dict):
            package_errors.append(f"{label} must be an object")
            continue
        eval_id = result.get("eval_id")
        if not is_nonempty_string(eval_id):
            package_errors.append(f"{label}.eval_id is required")
            continue
        if eval_id in received:
            package_errors.append(f"duplicate result for eval {eval_id!r}")
            continue
        received[eval_id] = result

    unknown_ids = sorted(set(received) - set(catalog_by_id))
    missing_ids = sorted(set(catalog_by_id) - set(received))
    if unknown_ids:
        package_errors.append(f"unknown eval ids: {unknown_ids}")
    if missing_ids:
        package_errors.append(f"missing eval ids: {missing_ids}")

    eval_reports: list[dict[str, Any]] = []
    assertion_summary = {"pass": 0, "fail": 0, "not_assessed": 0, "missing": 0}
    for item in catalog["evals"]:
        eval_id = item["id"]
        expected = expected_assertions(item)
        result = received.get(eval_id)
        if result is None:
            assertion_summary["missing"] += len(expected)
            eval_reports.append(
                {
                    "eval_id": eval_id,
                    "status": "FAIL",
                    "coverage": "missing",
                    "assertions": [
                        {
                            "assertion_id": item_id,
                            "description": description,
                            "status": "missing",
                        }
                        for item_id, description in expected.items()
                    ],
                }
            )
            continue

        local_errors: list[str] = []
        if not is_nonempty_string(result.get("response")):
            local_errors.append("response must be a non-empty string")
        raw_assertions = result.get("assertions")
        if not isinstance(raw_assertions, list):
            raw_assertions = []
            local_errors.append("assertions must be an array")

        received_assertions: dict[str, dict[str, Any]] = {}
        for assertion_position, assertion in enumerate(raw_assertions):
            label = f"assertions[{assertion_position}]"
            if not isinstance(assertion, dict):
                local_errors.append(f"{label} must be an object")
                continue
            item_id = assertion.get("assertion_id")
            if not is_nonempty_string(item_id):
                local_errors.append(f"{label}.assertion_id is required")
                continue
            if item_id in received_assertions:
                local_errors.append(f"duplicate assertion {item_id!r}")
                continue
            received_assertions[item_id] = assertion

        extra_assertions = sorted(set(received_assertions) - set(expected))
        missing_assertions = sorted(set(expected) - set(received_assertions))
        if extra_assertions:
            local_errors.append(f"unknown assertions: {extra_assertions}")
        if missing_assertions:
            local_errors.append(f"missing assertions: {missing_assertions}")

        assertion_reports: list[dict[str, Any]] = []
        for item_id, description in expected.items():
            assertion = received_assertions.get(item_id)
            if assertion is None:
                assertion_summary["missing"] += 1
                assertion_reports.append(
                    {
                        "assertion_id": item_id,
                        "description": description,
                        "status": "missing",
                    }
                )
                continue
            status = assertion.get("status")
            evidence = assertion.get("evidence")
            if status not in BEHAVIORAL_STATUSES:
                local_errors.append(
                    f"{item_id}.status must be pass, fail, or not-assessed"
                )
                normalized_status = "fail"
            else:
                normalized_status = status
            if not is_nonempty_string(evidence) or is_unfilled_template_value(
                evidence
            ):
                local_errors.append(f"{item_id}.evidence is required")
                normalized_status = "fail"
            assertion_summary[
                "not_assessed"
                if normalized_status == "not-assessed"
                else normalized_status
            ] += 1
            assertion_reports.append(
                {
                    "assertion_id": item_id,
                    "description": description,
                    "status": normalized_status,
                    "evidence": evidence if isinstance(evidence, str) else "",
                }
            )

        passed = (
            not local_errors
            and all(
                assertion["status"] == "pass"
                for assertion in assertion_reports
            )
        )
        eval_report: dict[str, Any] = {
            "eval_id": eval_id,
            "status": "PASS" if passed else "FAIL",
            "coverage": (
                "complete"
                if not missing_assertions and not extra_assertions
                else "incomplete"
            ),
            "assertions": assertion_reports,
        }
        if local_errors:
            eval_report["errors"] = local_errors
        eval_reports.append(eval_report)

    passed_evals = sum(item["status"] == "PASS" for item in eval_reports)
    failed_evals = len(eval_reports) - passed_evals
    package_complete = not package_errors and not missing_ids and not unknown_ids
    return {
        "schema": REPORT_SCHEMA,
        "mode": "behavioral",
        "status": (
            "PASS" if package_complete and failed_evals == 0 else "FAIL"
        ),
        "assessment_basis": "externally-produced-agent-results",
        "external_agent_invoked_by_runner": False,
        "behavioral_assertions_independently_verified_by_runner": False,
        "catalog_sha256": file_sha256(catalog_path),
        "run_id": payload["run_id"],
        "producer": payload["producer"],
        "summary": {
            "evals_expected": len(catalog["evals"]),
            "evals_received": len(received),
            "evals_pass": passed_evals,
            "evals_fail": failed_evals,
            "assertions_pass": assertion_summary["pass"],
            "assertions_fail": assertion_summary["fail"],
            "assertions_not_assessed": assertion_summary["not_assessed"],
            "assertions_missing": assertion_summary["missing"],
        },
        "package_errors": package_errors,
        "evals": eval_reports,
    }


def serialize_json(payload: dict[str, Any], pretty: bool) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2 if pretty else None,
        sort_keys=False,
    ) + "\n"


def write_output(
    payload: dict[str, Any],
    *,
    output: Optional[Path],
    pretty: bool,
    protected_paths: list[Path],
) -> None:
    rendered = serialize_json(payload, pretty)
    if output is None:
        sys.stdout.write(rendered)
        return

    try:
        parent = output.parent.resolve(strict=True)
    except OSError as exc:
        raise EvalInputError(f"output parent does not exist: {exc}") from exc
    if not parent.is_dir():
        raise EvalInputError("output parent must be a directory")
    resolved_output = parent / output.name
    if output.exists() and output.is_symlink():
        raise EvalInputError("refusing to overwrite a symbolic-link output")
    protected = {path.resolve() for path in protected_paths}
    if resolved_output.resolve(strict=False) in protected:
        raise EvalInputError("output must not overwrite an input file")

    temporary_name: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_name = handle.name
        os.replace(temporary_name, resolved_output)
    except OSError as exc:
        if temporary_name:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass
        raise EvalInputError(f"cannot write eval output: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run deterministic SciPlot probes or validate an external-agent "
            "behavioral result package. This runner never calls a model."
        )
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
        subparser.add_argument("--output", type=Path)
        subparser.add_argument("--pretty", action="store_true")

    deterministic = subparsers.add_parser(
        "deterministic",
        help="Execute allowlisted read-only probes and assert their JSON output.",
    )
    add_common(deterministic)

    behavioral = subparsers.add_parser(
        "behavioral",
        help="Validate externally produced agent results; no agent is invoked.",
    )
    add_common(behavioral)
    behavioral.add_argument("--results", type=Path, required=True)

    template = subparsers.add_parser(
        "template",
        help="Emit a catalog-bound behavioral result template.",
    )
    add_common(template)
    return parser


def error_report(mode: Optional[str], message: str) -> dict[str, Any]:
    return {
        "schema": REPORT_SCHEMA,
        "mode": mode or "unknown",
        "status": "FAIL",
        "assessment_basis": "input-validation",
        "external_agent_invoked_by_runner": False,
        "error": message,
    }


def main() -> int:
    args = build_parser().parse_args()
    protected_paths = [args.catalog]
    if getattr(args, "results", None) is not None:
        protected_paths.append(args.results)
    try:
        catalog = validate_catalog(read_json_object(args.catalog, "eval catalog"))
        if args.mode == "deterministic":
            report = run_deterministic(catalog, args.catalog)
            exit_code = 0 if report["status"] == "PASS" else 1
        elif args.mode == "behavioral":
            results = read_json_object(args.results, "behavioral results")
            report = validate_behavioral_results(
                results, catalog, args.catalog
            )
            exit_code = 0 if report["status"] == "PASS" else 1
        else:
            report = behavioral_template(catalog, args.catalog)
            exit_code = 0
        write_output(
            report,
            output=args.output,
            pretty=args.pretty,
            protected_paths=protected_paths,
        )
        return exit_code
    except EvalInputError as exc:
        report = error_report(args.mode, str(exc))
        try:
            write_output(
                report,
                output=None,
                pretty=getattr(args, "pretty", False),
                protected_paths=[],
            )
        except EvalInputError:
            pass
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
