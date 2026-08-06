#!/usr/bin/env python3
"""Generate explicitly synthetic smoke-test inputs for selected case sources."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sys
from pathlib import Path
from typing import Callable


SUPPORTED_CASES = {
    "rf-0001": "faceted_stacked_bar_data.csv",
    "rf-0178": "data.csv",
}
DEFAULT_SEEDS = {"rf-0001": 123, "rf-0178": 20260805}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_targets_absent(paths: list[Path]) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise ValueError(
            "refusing to overwrite existing demo files: " + ", ".join(existing)
        )


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def generate_rf_0001(output_dir: Path, seed: int) -> list[Path]:
    rng = random.Random(seed)
    days = ["Day 0", "Day 7", "Day 10", "Day 31"]
    microbes = [f"Microbe_{index}" for index in range(1, 11)]
    rows: list[dict[str, object]] = []
    for day_index, day in enumerate(days):
        for sample_id in range(1, 7):
            weights = []
            for microbe_index in range(10):
                baseline = 0.45 + (microbe_index >= 6) * 3.8
                time_effect = 1.0 + 0.12 * day_index * ((microbe_index % 3) - 1)
                weights.append(rng.gammavariate(max(0.1, baseline * time_effect), 1.0))
            total = sum(weights)
            for microbe, weight in zip(microbes, weights):
                rows.append(
                    {
                        "source_type": "simulated",
                        "source_seed": seed,
                        "sample_id": sample_id,
                        "day": day,
                        "microbe": microbe,
                        "relative_abundance": f"{weight / total:.12g}",
                    }
                )
    path = output_dir / SUPPORTED_CASES["rf-0001"]
    write_csv(
        path,
        [
            "source_type",
            "source_seed",
            "sample_id",
            "day",
            "microbe",
            "relative_abundance",
        ],
        rows,
    )
    return [path]


def generate_rf_0178(output_dir: Path, seed: int) -> list[Path]:
    rng = random.Random(seed)
    rows: list[dict[str, object]] = []
    group_offsets = {"WGS": 0.05, "MAG": -0.04, "SAG": -0.10}
    record_id = 1
    for group, offset in group_offsets.items():
        for _ in range(45):
            length = 10 ** rng.uniform(5.85, 7.05)
            log_noise = rng.gauss(0.0, 0.11)
            cds = max(120.0, (length / 1050.0) * math.exp(offset + log_noise))
            completeness = min(100.0, max(70.0, rng.gauss(96 if group == "WGS" else 88, 6)))
            rows.append(
                {
                    "record_id": f"SYN-{record_id:04d}",
                    "completeness": f"{completeness:.3f}",
                    "number_of_cds": f"{cds:.3f}",
                    "type": group,
                    "length": f"{length:.3f}",
                    "source_type": "simulated",
                    "source_seed": seed,
                }
            )
            record_id += 1
    path = output_dir / SUPPORTED_CASES["rf-0178"]
    write_csv(
        path,
        [
            "record_id",
            "completeness",
            "number_of_cds",
            "type",
            "length",
            "source_type",
            "source_seed",
        ],
        rows,
    )
    return [path]


GENERATORS: dict[str, Callable[[Path, int], list[Path]]] = {
    "rf-0001": generate_rf_0001,
    "rf-0178": generate_rf_0178,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate synthetic inputs for smoke tests only. "
            "Never use generated values as manuscript evidence."
        )
    )
    parser.add_argument("case_id", nargs="?", choices=sorted(SUPPORTED_CASES))
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--seed", type=int)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.list:
        print(json.dumps(SUPPORTED_CASES, ensure_ascii=False, indent=2))
        return 0
    if not args.case_id or not args.output_dir:
        print("generation requires CASE_ID and --output-dir", file=sys.stderr)
        return 2

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    seed = args.seed if args.seed is not None else DEFAULT_SEEDS[args.case_id]
    if args.case_id == "rf-0001" and seed != 123:
        print(
            "demo generation failed: rf-0001 source validates the original "
            "reproduction seed and therefore requires --seed 123",
            file=sys.stderr,
        )
        return 2
    targets = [output_dir / SUPPORTED_CASES[args.case_id], output_dir / "demo-data.json"]
    try:
        ensure_targets_absent(targets)
        generated = GENERATORS[args.case_id](output_dir, seed)
        manifest = {
            "schema_version": "0.1.0",
            "case_id": args.case_id,
            "synthetic": True,
            "production_use_allowed": False,
            "seed": seed,
            "files": [
                {
                    "name": path.name,
                    "sha256": sha256(path),
                    "bytes": path.stat().st_size,
                }
                for path in generated
            ],
            "warning": (
                "These values exist only to test rendering and input guards. "
                "They are not scientific evidence."
            ),
        }
        manifest_path = output_dir / "demo-data.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        print(f"demo generation failed: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "status": "generated",
                "case_id": args.case_id,
                "output_dir": str(output_dir),
                "files": [str(path) for path in generated],
                "manifest": str(manifest_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
