#!/usr/bin/env python3
"""Perform lightweight, non-rendering SciPlot environment diagnostics."""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

from run_implementation_smoke import (
    DEFAULT_INDEX,
    SKILL_ROOT,
    SmokeConfigurationError,
    discover_verified,
)


SCHEMA = "sciplot.doctor-report/v1"
MINIMUM_PYTHON = (3, 9)
REQUIREMENT = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9_.-]*)(?:\s*>=\s*([0-9]+(?:\.[0-9]+)*))?\s*$"
)
IMPORT_NAMES = {
    "matplotlib": "matplotlib",
    "numpy": "numpy",
    "pandas": "pandas",
    "pillow": "PIL",
    "pyyaml": "yaml",
}


def _version_tuple(value: str) -> tuple[int, ...]:
    match = re.match(r"^([0-9]+(?:\.[0-9]+)*)", value)
    return tuple(map(int, match.group(1).split("."))) if match else ()


def _check(
    checks: list[dict[str, Any]],
    check_id: str,
    status: str,
    message: str,
    **details: Any,
) -> None:
    item: dict[str, Any] = {
        "id": check_id,
        "status": status,
        "message": message,
    }
    if details:
        item["details"] = details
    checks.append(item)


def _requirements(targets: Iterable[Any]) -> dict[str, Optional[str]]:
    requirements: dict[str, Optional[str]] = {}
    for target in targets:
        backend = target.manifest.get("backend", {})
        raw = backend.get("requires", []) if isinstance(backend, dict) else []
        if not isinstance(raw, list):
            raise SmokeConfigurationError(
                f"{target.implementation_id}: backend.requires must be an array"
            )
        for value in raw:
            if not isinstance(value, str):
                raise SmokeConfigurationError(
                    f"{target.implementation_id}: invalid runtime requirement"
                )
            match = REQUIREMENT.fullmatch(value)
            if match is None:
                raise SmokeConfigurationError(
                    f"{target.implementation_id}: unsupported requirement syntax "
                    f"{value!r}"
                )
            name, minimum = match.groups()
            if name.lower() == "python":
                continue
            normalized = name.lower()
            current = requirements.get(normalized)
            if minimum is not None and (
                current is None
                or _version_tuple(minimum) > _version_tuple(current)
            ):
                requirements[normalized] = minimum
            else:
                requirements.setdefault(normalized, current)
    return requirements


def diagnose(
    *,
    skill_root: Path = SKILL_ROOT,
    index_path: Optional[Path] = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    current_python = sys.version_info[:3]
    python_ok = current_python >= MINIMUM_PYTHON
    _check(
        checks,
        "DR-PYTHON",
        "PASS" if python_ok else "FAIL",
        (
            f"Python {current_python[0]}.{current_python[1]}."
            f"{current_python[2]} is supported"
            if python_ok
            else "SciPlot requires Python 3.9 or newer"
        ),
        current=list(current_python),
        minimum=list(MINIMUM_PYTHON),
    )

    root = skill_root.resolve()
    index = index_path or root / "implementations" / "implementation-index.json"
    try:
        targets = discover_verified(skill_root=root, index_path=index)
    except (OSError, json.JSONDecodeError, SmokeConfigurationError) as exc:
        _check(
            checks,
            "DR-CATALOG",
            "FAIL",
            "verified implementation catalog is not runnable",
            error=str(exc),
        )
        targets = []
    else:
        _check(
            checks,
            "DR-CATALOG",
            "PASS",
            f"{len(targets)} verified implementation profile(s) are path-safe",
            implementations=[target.implementation_id for target in targets],
        )

    try:
        requirements = _requirements(targets)
    except SmokeConfigurationError as exc:
        _check(
            checks,
            "DR-REQUIREMENTS",
            "FAIL",
            "runtime requirements are not machine-checkable",
            error=str(exc),
        )
        requirements = {}
    for package, minimum in sorted(requirements.items()):
        import_name = IMPORT_NAMES.get(package, package.replace("-", "_"))
        if importlib.util.find_spec(import_name) is None:
            _check(
                checks,
                f"DR-PACKAGE-{package.upper()}",
                "FAIL",
                f"required package {package} is not importable",
                minimum=minimum,
                import_name=import_name,
            )
            continue
        try:
            installed = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            installed = None
        adequate = minimum is None or (
            installed is not None
            and _version_tuple(installed) >= _version_tuple(minimum)
        )
        _check(
            checks,
            f"DR-PACKAGE-{package.upper()}",
            "PASS" if adequate else "FAIL",
            (
                f"{package} {installed or '(version unavailable)'} is importable"
                if adequate
                else (
                    f"{package} version metadata is unavailable; "
                    f"cannot verify required minimum {minimum}"
                    if installed is None
                    else f"{package} {installed} is older than required {minimum}"
                )
            ),
            minimum=minimum,
            installed=installed,
            import_name=import_name,
        )

    for target in targets:
        language = str(target.manifest.get("backend", {}).get("language", "")).lower()
        if language in {"r", "rscript"}:
            available = shutil.which("Rscript")
            _check(
                checks,
                f"DR-RUNTIME-{target.implementation_id}",
                "PASS" if available else "FAIL",
                (
                    f"Rscript runtime found for {target.implementation_id}"
                    if available
                    else f"Rscript runtime missing for {target.implementation_id}"
                ),
                executable=available,
            )

    failed = [item for item in checks if item["status"] == "FAIL"]
    return {
        "schema_version": SCHEMA,
        "status": "PASS" if not failed else "FAIL",
        "mode": "lightweight-no-render",
        "summary": {
            "pass": sum(item["status"] == "PASS" for item in checks),
            "warn": sum(item["status"] == "WARN" for item in checks),
            "fail": len(failed),
        },
        "checks": checks,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Check Python, required packages, and verified implementation "
            "metadata/profile safety without rendering figures."
        )
    )
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = diagnose(skill_root=SKILL_ROOT, index_path=args.index)
    rendered = json.dumps(
        report,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
    ) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        if args.output.resolve(strict=False) == args.index.resolve(strict=False):
            sys.stdout.write(
                json.dumps(
                    {
                        "schema_version": SCHEMA,
                        "status": "FAIL",
                        "error": "output must not overwrite the implementation index",
                    }
                )
                + "\n"
            )
            return 2
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            sys.stdout.write(
                json.dumps(
                    {
                        "schema_version": SCHEMA,
                        "status": "FAIL",
                        "error": str(exc),
                    }
                )
                + "\n"
            )
            return 2
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
