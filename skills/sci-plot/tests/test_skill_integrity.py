from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SkillIntegrityTests(unittest.TestCase):
    def test_skill_frontmatter_is_minimal(self) -> None:
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        _, frontmatter, _ = text.split("---", 2)
        keys = {
            line.split(":", 1)[0].strip()
            for line in frontmatter.splitlines()
            if line.strip() and not line.startswith((" ", "\t"))
        }
        self.assertEqual(keys, {"name", "description"})
        self.assertRegex(frontmatter, r"(?m)^name:\s*sci-plot\s*$")

    def test_openai_metadata_matches_skill(self) -> None:
        text = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn('display_name: "SciPlot｜科研绘图"', text)
        self.assertIn("$sci-plot", text)
        match = re.search(r'short_description:\s*"([^"]+)"', text)
        self.assertIsNotNone(match)
        self.assertGreaterEqual(len(match.group(1)), 25)
        self.assertLessEqual(len(match.group(1)), 64)

    def test_markdown_local_links_exist(self) -> None:
        missing: list[str] = []
        link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for markdown in ROOT.rglob("*.md"):
            for target in link_pattern.findall(markdown.read_text(encoding="utf-8")):
                target = target.strip().split("#", 1)[0]
                if not target or "://" in target or target.startswith(("mailto:", "#")):
                    continue
                candidate = (markdown.parent / target).resolve()
                if not candidate.exists():
                    missing.append(f"{markdown.relative_to(ROOT)} -> {target}")
        self.assertEqual(missing, [])

    def test_case_catalog_assets_and_cards_agree(self) -> None:
        payload = json.loads(
            (ROOT / "references" / "case-index.json").read_text(encoding="utf-8")
        )
        cases = payload["cases"]
        ids = [case["id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 18)
        for case in cases:
            self.assertIn("audit_status", case)
            self.assertIn("implementation_status", case)
            self.assertTrue((ROOT / case["asset"]).is_file(), case["id"])

        cards = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                ROOT / "references" / "cases-core.md",
                ROOT / "references" / "cases-extensions.md",
            )
        )
        card_ids = set(re.findall(r"^## `([^`]+)`", cards, re.MULTILINE))
        self.assertEqual(set(ids), card_ids)

    def test_eval_catalog_is_valid(self) -> None:
        payload = json.loads((ROOT / "evals" / "evals.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["skill_name"], "sci-plot")
        ids = [item["id"] for item in payload["evals"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 10)
        for item in payload["evals"]:
            self.assertTrue(item["prompt"].strip())
            self.assertTrue(item["expected"])

    def test_no_platform_junk_is_packaged(self) -> None:
        self.assertEqual(list(ROOT.rglob(".DS_Store")), [])


if __name__ == "__main__":
    unittest.main()
