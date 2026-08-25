#!/usr/bin/env python3
"""Search the public academic-figure case index without external packages."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = SKILL_ROOT / "references" / "cases" / "case-index.jsonl"
DEFAULT_PROMPTS = SKILL_ROOT / "references" / "cases" / "case-prompts.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find scientifically and structurally relevant figure cases."
    )
    parser.add_argument("query", help="Research question, data structure, chart name, or case ID")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--category")
    parser.add_argument("--domain")
    parser.add_argument("--language", choices=["python", "r"])
    parser.add_argument("--open-only", action="store_true")
    parser.add_argument("--include-prompt", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--prompts", type=Path, default=DEFAULT_PROMPTS)
    return parser.parse_args()


def normalize(text: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u3400-\u9fff]+", " ", text.lower()).strip()


def query_terms(query: str) -> list[str]:
    normalized = normalize(query)
    words = [word for word in normalized.split() if word]
    chinese = "".join(char for char in normalized if "\u3400" <= char <= "\u9fff")
    grams = [chinese[i : i + 2] for i in range(max(0, len(chinese) - 1))]
    return list(dict.fromkeys(words + grams))


def load_index(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def load_prompts(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    bundle = json.loads(path.read_text(encoding="utf-8"))
    return {item["caseId"]: item for item in bundle.get("recipes", [])}


def field_text(record: dict[str, Any], field: str) -> str:
    value = record.get(field, "")
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


def score(record: dict[str, Any], query: str, terms: list[str]) -> float:
    exact_query = normalize(query)
    weights = {
        "id": 16.0,
        "title": 12.0,
        "aliases": 9.0,
        "researchGoals": 7.0,
        "category": 6.0,
        "chartTypes": 6.0,
        "dataShapes": 5.0,
        "relationshipHints": 5.0,
        "description": 3.0,
        "domains": 2.0,
    }
    total = 0.0
    for field, weight in weights.items():
        text = normalize(field_text(record, field))
        if exact_query and exact_query in text:
            total += weight * 2.0
        for term in terms:
            if term in text:
                total += weight
    # Availability is only a tie-breaker after a semantic match; it must not
    # make an unrelated open template appear as a search result.
    if total > 0:
        if record.get("releaseTier") == "open-template":
            total += 0.5
        elif record.get("curation", {}).get("templateCandidate"):
            total += 0.25
    return total


def matches_filters(record: dict[str, Any], args: argparse.Namespace) -> bool:
    if args.category and args.category != record.get("category"):
        return False
    if args.domain and args.domain not in record.get("domains", []):
        return False
    if args.open_only:
        implementations = record.get("openImplementation", {})
        if args.language:
            return bool(implementations.get(args.language))
        return any(implementations.values())
    if args.language and record.get("releaseTier") == "open-template":
        return bool(record.get("openImplementation", {}).get(args.language))
    return True


def compact_result(record: dict[str, Any], result_score: float) -> dict[str, Any]:
    return {
        "id": record["id"],
        "title": record["title"],
        "score": round(result_score, 2),
        "category": record.get("category"),
        "chartTypes": record.get("chartTypes", []),
        "researchGoals": record.get("researchGoals", []),
        "dataShapes": record.get("dataShapes", []),
        "relationshipHints": record.get("relationshipHints", []),
        "description": record.get("description"),
        "previews": record.get("previews", []),
        "releaseTier": record.get("releaseTier"),
        "openImplementation": record.get("openImplementation", {}),
        "templatePath": record.get("templatePath"),
        "curation": record.get("curation", {}),
    }


def main() -> int:
    args = parse_args()
    if not args.index.exists():
        print(f"Case index not found: {args.index}", file=sys.stderr)
        return 2

    records = load_index(args.index)
    terms = query_terms(args.query)
    ranked = []
    for record in records:
        if not matches_filters(record, args):
            continue
        result_score = score(record, args.query, terms)
        if result_score > 0:
            ranked.append((result_score, record))
    ranked.sort(key=lambda item: (-item[0], item[1]["number"]))

    prompts = load_prompts(args.prompts) if args.include_prompt else {}
    results = []
    for result_score, record in ranked[: max(args.limit, 1)]:
        item = compact_result(record, result_score)
        if args.include_prompt:
            recipe = prompts.get(record["promptKey"], {})
            if args.language:
                item["prompt"] = recipe.get("prompts", {}).get(args.language)
            else:
                item["prompts"] = recipe.get("prompts", {})
        results.append(item)

    if args.as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for index, item in enumerate(results, start=1):
            chart_types = "、".join(item["chartTypes"])
            print(f"{index}. {item['id']} · {item['title']} · {item['category']} · {chart_types}")
            print(f"   {item['description']}")
            if item["previews"]:
                print(f"   preview: {item['previews'][0]['asset']}")
            if any(item["openImplementation"].values()):
                languages = [key for key, value in item["openImplementation"].items() if value]
                print(f"   open implementation: {', '.join(languages)}")
                if item.get("templatePath"):
                    print(f"   template: {item['templatePath']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
