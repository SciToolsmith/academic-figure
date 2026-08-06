#!/usr/bin/env python3
"""Run every verified SciPlot-native implementation from a safe smoke profile.

The runner deliberately accepts argv arrays, never shell command strings. Each
verified implementation owns ``verification/smoke-profile.json`` next to its
local smoke evidence. The preferred profile shape is::

    {
      "schema_version": "sciplot.smoke-profile/v1",
      "argv": [
        "render.py",
        "--input",
        "implementations/python/example-v1/examples/demo.csv",
        "--output-dir",
        "{output_dir}"
      ]
    }

``argv[0]`` must exactly match ``backend.entrypoint`` in the implementation
manifest. All repository inputs are skill-root-relative; ``{output_dir}`` must
appear exactly once as its own token. No shell is involved at any point.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Union


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = SKILL_ROOT / "implementations" / "implementation-index.json"
PROFILE_SCHEMA = "sciplot.smoke-profile/v1"
REPORT_SCHEMA = "sciplot.implementation-smoke-report/v1"
OUTPUT_PLACEHOLDER = "{output_dir}"
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SHELL_META = re.compile(r"[\x00-\x1f;&|`$><\\\"']")
PATH_OPTIONS = {"--input", "--data-manifest", "--figure-contract"}
MAX_CAPTURE_CHARS = 40_000


class SmokeConfigurationError(ValueError):
    """Raised when an index, manifest, or smoke profile is unsafe."""


@dataclass(frozen=True)
class SmokeTarget:
    """One validated implementation ready for a smoke run."""

    implementation_id: str
    manifest_path: Path
    manifest: dict[str, Any]
    pack_dir: Path
    entrypoint: Path
    profile_path: Path
    argv: tuple[str, ...]
    interpreter: tuple[str, ...]


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SmokeConfigurationError(f"cannot read {label}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SmokeConfigurationError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SmokeConfigurationError(f"{label} must be a JSON object")
    return payload


def _inside(root: Path, candidate: Path, label: str) -> Path:
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise SmokeConfigurationError(f"{label} escapes {resolved_root}") from exc
    return resolved


def _safe_relative(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise SmokeConfigurationError(f"{label} must be a non-empty relative path")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise SmokeConfigurationError(f"{label} is unsafe: {value!r}")
    return _inside(root, root / relative, label)


def _runtime_for(language: Any) -> tuple[str, ...]:
    normalized = str(language).strip().lower()
    if normalized == "python":
        return (sys.executable,)
    if normalized in {"r", "rscript"}:
        executable = shutil.which("Rscript")
        if executable is None:
            raise SmokeConfigurationError(
                "verified R implementation requires Rscript on PATH"
            )
        return (executable,)
    raise SmokeConfigurationError(
        f"unsupported verified implementation language: {language!r}"
    )


def _validate_token(token: Any, position: int) -> str:
    if not isinstance(token, str) or not token:
        raise SmokeConfigurationError(
            f"profile argv[{position}] must be a non-empty string"
        )
    if token == OUTPUT_PLACEHOLDER:
        return token
    if OUTPUT_PLACEHOLDER in token:
        raise SmokeConfigurationError(
            f"{OUTPUT_PLACEHOLDER} must be a standalone argv token"
        )
    if SHELL_META.search(token) or any(char in token for char in "*?["):
        raise SmokeConfigurationError(
            f"profile argv[{position}] contains a shell metacharacter"
        )
    path_like = (
        token.split("=", 1)[1]
        if token.startswith("-") and "=" in token
        else token
    )
    candidate = Path(path_like)
    if candidate.is_absolute() or ".." in token:
        raise SmokeConfigurationError(
            f"profile argv[{position}] contains an unsafe path: {token!r}"
        )
    return token


def _validate_repository_inputs(
    argv: tuple[str, ...],
    skill_root: Path,
) -> None:
    for option in PATH_OPTIONS:
        positions = [index for index, value in enumerate(argv) if value == option]
        if len(positions) != 1:
            raise SmokeConfigurationError(
                f"profile must contain {option} exactly once"
            )
        position = positions[0]
        if position + 1 >= len(argv):
            raise SmokeConfigurationError(f"profile {option} has no value")
        value = argv[position + 1]
        path = _safe_relative(skill_root, value, f"profile {option}")
        if not path.is_file():
            raise SmokeConfigurationError(
                f"profile {option} does not exist: {value!r}"
            )


def load_profile(
    profile_path: Path,
    *,
    expected_entrypoint: str,
    skill_root: Path,
) -> tuple[str, ...]:
    """Load and validate one non-shell smoke profile."""

    profile = _load_object(profile_path, "smoke profile")
    if profile.get("schema_version") != PROFILE_SCHEMA:
        raise SmokeConfigurationError(
            f"smoke profile must use {PROFILE_SCHEMA}"
        )
    if set(profile) != {"schema_version", "argv"}:
        raise SmokeConfigurationError(
            "smoke profile supports only schema_version and argv"
        )
    raw_argv = profile.get("argv")
    if not isinstance(raw_argv, list) or len(raw_argv) < 3:
        raise SmokeConfigurationError(
            "smoke profile argv must be a structured array with at least 3 items"
        )
    argv = tuple(
        _validate_token(token, position)
        for position, token in enumerate(raw_argv)
    )
    if argv[0] != expected_entrypoint:
        raise SmokeConfigurationError(
            "smoke profile argv[0] must exactly match backend.entrypoint"
        )
    if argv.count(OUTPUT_PLACEHOLDER) != 1:
        raise SmokeConfigurationError(
            f"smoke profile must contain {OUTPUT_PLACEHOLDER} exactly once"
        )
    output_position = argv.index(OUTPUT_PLACEHOLDER)
    if output_position == 0 or argv[output_position - 1] != "--output-dir":
        raise SmokeConfigurationError(
            f"{OUTPUT_PLACEHOLDER} must be the value of --output-dir"
        )
    if argv.count("--output-dir") != 1:
        raise SmokeConfigurationError(
            "smoke profile must contain --output-dir exactly once"
        )
    _validate_repository_inputs(argv, skill_root)
    return argv


def discover_verified(
    *,
    skill_root: Path = SKILL_ROOT,
    index_path: Optional[Path] = None,
) -> list[SmokeTarget]:
    """Discover and fully validate all ``status=verified`` index entries."""

    root = skill_root.resolve()
    index = (index_path or root / "implementations" / "implementation-index.json")
    index = _inside(root, index, "implementation index")
    payload = _load_object(index, "implementation index")
    entries = payload.get("implementations")
    if not isinstance(entries, list):
        raise SmokeConfigurationError(
            "implementation index implementations must be an array"
        )
    verified = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("status") == "verified"
    ]
    if not verified:
        raise SmokeConfigurationError(
            "implementation index contains no verified implementations"
        )

    targets: list[SmokeTarget] = []
    seen: set[str] = set()
    implementations_root = (root / "implementations").resolve()
    for entry in verified:
        implementation_id = entry.get("id")
        if not isinstance(implementation_id, str) or not SAFE_ID.fullmatch(
            implementation_id
        ):
            raise SmokeConfigurationError(
                f"unsafe verified implementation id: {implementation_id!r}"
            )
        if implementation_id in seen:
            raise SmokeConfigurationError(
                f"duplicate verified implementation id: {implementation_id}"
            )
        seen.add(implementation_id)

        manifest_path = _safe_relative(
            root,
            entry.get("manifest"),
            f"{implementation_id} manifest",
        )
        _inside(implementations_root, manifest_path, f"{implementation_id} manifest")
        if not manifest_path.is_file():
            raise SmokeConfigurationError(
                f"{implementation_id} manifest does not exist"
            )
        manifest = _load_object(
            manifest_path, f"{implementation_id} implementation manifest"
        )
        for field in ("id", "version", "status"):
            if manifest.get(field) != entry.get(field):
                raise SmokeConfigurationError(
                    f"{implementation_id} {field} differs between index and manifest"
                )

        pack_dir = manifest_path.parent.resolve()
        backend = manifest.get("backend")
        if not isinstance(backend, dict):
            raise SmokeConfigurationError(
                f"{implementation_id} backend must be an object"
            )
        entrypoint_name = backend.get("entrypoint")
        entrypoint = _safe_relative(
            pack_dir,
            entrypoint_name,
            f"{implementation_id} entrypoint",
        )
        _inside(pack_dir, entrypoint, f"{implementation_id} entrypoint")
        if not entrypoint.is_file():
            raise SmokeConfigurationError(
                f"{implementation_id} entrypoint does not exist"
            )
        interpreter = _runtime_for(backend.get("language"))

        profile_path = pack_dir / "verification" / "smoke-profile.json"
        profile_path = _inside(pack_dir, profile_path, f"{implementation_id} profile")
        if not profile_path.is_file():
            raise SmokeConfigurationError(
                f"{implementation_id} is verified but has no "
                "verification/smoke-profile.json"
            )
        argv = load_profile(
            profile_path,
            expected_entrypoint=str(entrypoint_name),
            skill_root=root,
        )
        targets.append(
            SmokeTarget(
                implementation_id=implementation_id,
                manifest_path=manifest_path,
                manifest=manifest,
                pack_dir=pack_dir,
                entrypoint=entrypoint,
                profile_path=profile_path,
                argv=argv,
                interpreter=interpreter,
            )
        )
    return targets


def _trim(value: Optional[Union[str, bytes]]) -> str:
    if value is None:
        return ""
    text = value.decode("utf-8", "replace") if isinstance(value, bytes) else value
    if len(text) <= MAX_CAPTURE_CHARS:
        return text
    return text[:MAX_CAPTURE_CHARS] + "\n...[truncated by smoke runner]..."


def _command_record(command: Iterable[str], root: Path) -> list[str]:
    recorded: list[str] = []
    for token in command:
        try:
            recorded.append(str(Path(token).resolve().relative_to(root.resolve())))
        except (OSError, ValueError):
            recorded.append(token)
    return recorded


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    env: dict[str, str],
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
        )
        return {
            "returncode": completed.returncode,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": _trim(completed.stdout),
            "stderr": _trim(completed.stderr),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": _trim(exc.stdout),
            "stderr": _trim(exc.stderr),
            "timed_out": True,
        }
    except OSError as exc:
        return {
            "returncode": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": "",
            "stderr": str(exc),
            "timed_out": False,
        }


def _write_log(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def _qa_command(
    name: str,
    command: list[str],
    *,
    skill_root: Path,
    timeout_seconds: float,
    env: dict[str, str],
    report_path: Optional[Path] = None,
) -> dict[str, Any]:
    result = _run_command(
        command,
        cwd=skill_root,
        timeout_seconds=timeout_seconds,
        env=env,
    )
    result["name"] = name
    result["command"] = _command_record(command, skill_root)
    if report_path is not None and result["stdout"] and not report_path.exists():
        report_path.write_text(result["stdout"], encoding="utf-8")
    return result


def run_qa_pipeline(
    target: SmokeTarget,
    *,
    output_dir: Path,
    skill_root: Path,
    timeout_seconds: float,
    env: dict[str, str],
) -> dict[str, Any]:
    """Apply the existing Contract, delivery, artifact, and unified QA gates."""

    verification = target.manifest.get("verification")
    outputs = target.manifest.get("outputs")
    if not isinstance(verification, dict) or not isinstance(outputs, dict):
        raise SmokeConfigurationError(
            f"{target.implementation_id}: verification/outputs must be objects"
        )
    contract = _safe_relative(
        skill_root,
        verification.get("figure_contract"),
        f"{target.implementation_id} figure contract",
    )
    if not contract.is_file():
        raise SmokeConfigurationError(
            f"{target.implementation_id}: Figure Contract does not exist"
        )
    basename = outputs.get("basename")
    formats = outputs.get("formats")
    render_manifest_name = outputs.get("manifest")
    data_validation_name = outputs.get("data_validation")
    if (
        not isinstance(basename, str)
        or not SAFE_ID.fullmatch(basename)
        or not isinstance(formats, list)
        or not formats
        or not all(
            isinstance(value, str)
            and value in {"svg", "pdf", "png", "tiff"}
            for value in formats
        )
        or not isinstance(render_manifest_name, str)
        or Path(render_manifest_name).name != render_manifest_name
        or not isinstance(data_validation_name, str)
        or Path(data_validation_name).name != data_validation_name
    ):
        raise SmokeConfigurationError(
            f"{target.implementation_id}: outputs cannot drive generic QA"
        )
    artifacts = [output_dir / f"{basename}.{value}" for value in formats]
    render_manifest = output_dir / render_manifest_name
    data_validation = output_dir / data_validation_name
    required = [*artifacts, render_manifest, data_validation]
    missing = [
        str(path.relative_to(output_dir))
        for path in required
        if not path.is_file()
    ]
    if missing:
        raise SmokeConfigurationError(
            f"{target.implementation_id}: renderer omitted required outputs {missing}"
        )

    contract_payload = _load_object(contract, "Figure Contract")
    target_geometry = contract_payload.get("target")
    if not isinstance(target_geometry, dict):
        raise SmokeConfigurationError(
            f"{target.implementation_id}: Figure Contract target is missing"
        )
    report_dir = output_dir / "_qa"
    report_dir.mkdir()
    contract_report = report_dir / "contract.json"
    delivery_report = report_dir / "delivery.json"
    artifact_report = report_dir / "artifacts.json"
    qa_report = report_dir / "qa.json"

    commands: list[dict[str, Any]] = []
    contract_command = [
        sys.executable,
        str(skill_root / "scripts" / "validate_contract.py"),
        str(contract),
        "--stage",
        "final",
        "--pretty",
    ]
    commands.append(
        _qa_command(
            "contract",
            contract_command,
            skill_root=skill_root,
            timeout_seconds=timeout_seconds,
            env=env,
            report_path=contract_report,
        )
    )
    if commands[-1]["returncode"] != 0:
        return {
            "status": "FAIL",
            "reports_dir": str(report_dir),
            "commands": commands,
            "error": "final Figure Contract gate failed",
        }

    delivery_command = [
        sys.executable,
        str(skill_root / "scripts" / "validate_delivery.py"),
        "--contract",
        str(contract),
        "--manifest",
        str(render_manifest),
        "--artifact-dir",
        str(output_dir),
        "--pretty",
        "--output",
        str(delivery_report),
    ]
    commands.append(
        _qa_command(
            "delivery",
            delivery_command,
            skill_root=skill_root,
            timeout_seconds=timeout_seconds,
            env=env,
        )
    )
    if commands[-1]["returncode"] != 0:
        return {
            "status": "FAIL",
            "reports_dir": str(report_dir),
            "commands": commands,
            "error": "delivery gate failed",
        }

    artifact_command = [
        sys.executable,
        str(skill_root / "scripts" / "inspect_artifacts.py"),
        *map(str, artifacts),
    ]
    for field, option in (
        ("width_mm", "--width-mm"),
        ("height_mm", "--height-mm"),
        ("resolution_dpi", "--dpi"),
    ):
        value = target_geometry.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            artifact_command.extend([option, str(value)])
    if "svg" in formats:
        artifact_command.append("--require-svg-text")
    artifact_command.extend(
        ["--strict", "--pretty", "--output", str(artifact_report)]
    )
    commands.append(
        _qa_command(
            "artifacts",
            artifact_command,
            skill_root=skill_root,
            timeout_seconds=timeout_seconds,
            env=env,
        )
    )
    if commands[-1]["returncode"] != 0:
        return {
            "status": "FAIL",
            "reports_dir": str(report_dir),
            "commands": commands,
            "error": "artifact gate failed",
        }

    qa_command = [
        sys.executable,
        str(skill_root / "scripts" / "build_qa_report.py"),
        str(contract_report),
        str(delivery_report),
        str(data_validation),
        str(artifact_report),
        "--strict",
        "--pretty",
        "--output",
        str(qa_report),
    ]
    commands.append(
        _qa_command(
            "unified-qa",
            qa_command,
            skill_root=skill_root,
            timeout_seconds=timeout_seconds,
            env=env,
        )
    )
    if commands[-1]["returncode"] != 0 or not qa_report.is_file():
        return {
            "status": "FAIL",
            "reports_dir": str(report_dir),
            "commands": commands,
            "error": "unified QA gate failed",
        }
    qa_payload = _load_object(qa_report, "unified QA report")
    non_pass = [
        check
        for check in qa_payload.get("checks", [])
        if isinstance(check, dict) and check.get("status") != "PASS"
    ]
    status = (
        "PASS"
        if qa_payload.get("status") == "PASS" and not non_pass
        else "FAIL"
    )
    return {
        "status": status,
        "reports_dir": str(report_dir),
        "qa_report": str(qa_report),
        "qa_summary": qa_payload.get("summary"),
        "non_pass_checks": non_pass,
        "commands": commands,
    }


def run_target(
    target: SmokeTarget,
    *,
    output_root: Path,
    skill_root: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    output_root = output_root.resolve()
    output_dir = output_root / target.implementation_id
    if output_dir.is_symlink():
        raise SmokeConfigurationError(
            f"refusing symbolic-link output directory: {output_dir}"
        )
    output_dir = _inside(
        output_root,
        output_dir,
        f"{target.implementation_id} output directory",
    )
    if output_dir.exists() and any(output_dir.iterdir()):
        raise SmokeConfigurationError(
            f"output directory is not empty: {output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    expanded = [
        str(output_dir) if token == OUTPUT_PLACEHOLDER else token
        for token in target.argv[1:]
    ]
    command = [*target.interpreter, str(target.entrypoint), *expanded]
    env = os.environ.copy()
    env.setdefault("MPLBACKEND", "Agg")
    mpl_config = output_root / "_matplotlib"
    mpl_config.mkdir(exist_ok=True)
    env.setdefault("MPLCONFIGDIR", str(mpl_config))
    renderer = _run_command(
        command,
        cwd=skill_root,
        timeout_seconds=timeout_seconds,
        env=env,
    )
    _write_log(output_dir / "renderer.stdout.log", renderer["stdout"])
    _write_log(output_dir / "renderer.stderr.log", renderer["stderr"])
    result: dict[str, Any] = {
        "id": target.implementation_id,
        "status": "FAIL",
        "manifest": str(target.manifest_path.relative_to(skill_root)),
        "profile": str(target.profile_path.relative_to(skill_root)),
        "entrypoint": str(target.entrypoint.relative_to(skill_root)),
        "output_dir": str(output_dir),
        "command": _command_record(command, skill_root),
        "renderer": renderer,
    }
    if renderer["returncode"] != 0:
        result["error"] = (
            "renderer timed out"
            if renderer["timed_out"]
            else "renderer returned a non-zero exit status"
        )
        return result
    try:
        qa = run_qa_pipeline(
            target,
            output_dir=output_dir,
            skill_root=skill_root,
            timeout_seconds=timeout_seconds,
            env=env,
        )
    except (OSError, json.JSONDecodeError, SmokeConfigurationError) as exc:
        result["error"] = f"QA configuration failed: {exc}"
        return result
    result["qa"] = qa
    result["status"] = "PASS" if qa["status"] == "PASS" else "FAIL"
    if result["status"] != "PASS":
        result["error"] = qa.get("error", "unified QA did not pass")
    return result


def run_all(
    *,
    skill_root: Path = SKILL_ROOT,
    index_path: Optional[Path] = None,
    output_root: Path,
    timeout_seconds: float = 180.0,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise SmokeConfigurationError("timeout_seconds must be greater than zero")
    root = skill_root.resolve()
    targets = discover_verified(skill_root=root, index_path=index_path)
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    implementations: list[dict[str, Any]] = []
    for target in targets:
        try:
            implementations.append(
                run_target(
                    target,
                    output_root=output_root,
                    skill_root=root,
                    timeout_seconds=timeout_seconds,
                )
            )
        except (OSError, SmokeConfigurationError) as exc:
            implementations.append(
                {
                    "id": target.implementation_id,
                    "status": "FAIL",
                    "error": str(exc),
                }
            )
    passed = sum(item["status"] == "PASS" for item in implementations)
    failed = len(implementations) - passed
    return {
        "schema_version": REPORT_SCHEMA,
        "status": "PASS" if failed == 0 else "FAIL",
        "assessment_basis": (
            "verified-index + structured-smoke-profile + existing-qa-gates"
        ),
        "shell_invoked": False,
        "summary": {
            "verified": len(implementations),
            "passed": passed,
            "failed": failed,
        },
        "implementations": implementations,
    }


def _same_file(left: Path, right: Path) -> bool:
    try:
        return left.resolve(strict=False) == right.resolve(strict=False)
    except (OSError, RuntimeError):
        return False


def write_report(
    report: dict[str, Any],
    *,
    output: Optional[Path],
    pretty: bool,
    protected: Iterable[Path],
) -> None:
    rendered = json.dumps(
        report,
        ensure_ascii=False,
        indent=2 if pretty else None,
    ) + "\n"
    if output is None:
        sys.stdout.write(rendered)
        return
    if any(_same_file(output, path) for path in protected):
        raise SmokeConfigurationError("report output must not overwrite an input")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise SmokeConfigurationError("refusing to overwrite a report symlink")
    temporary: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = handle.name
        os.replace(temporary, output)
    except OSError as exc:
        if temporary:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass
        raise SmokeConfigurationError(f"cannot write smoke report: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run all verified native implementations from structured, "
            "non-shell smoke profiles and apply the existing QA gates."
        )
    )
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="Fresh directory for rendered bundles and per-pack QA reports.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=180.0,
        help="Timeout applied independently to each subprocess (default: 180).",
    )
    parser.add_argument("--output", type=Path, help="Write the aggregate JSON report.")
    parser.add_argument("--pretty", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    protected = [args.index]
    try:
        report = run_all(
            skill_root=SKILL_ROOT,
            index_path=args.index,
            output_root=args.output_root,
            timeout_seconds=args.timeout_seconds,
        )
        write_report(
            report,
            output=args.output,
            pretty=args.pretty,
            protected=protected,
        )
        return 0 if report["status"] == "PASS" else 1
    except (OSError, json.JSONDecodeError, SmokeConfigurationError) as exc:
        report = {
            "schema_version": REPORT_SCHEMA,
            "status": "FAIL",
            "assessment_basis": "configuration-validation",
            "shell_invoked": False,
            "error": str(exc),
        }
        try:
            write_report(
                report,
                output=args.output,
                pretty=args.pretty,
                protected=protected,
            )
        except SmokeConfigurationError:
            sys.stdout.write(json.dumps(report, ensure_ascii=False) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
