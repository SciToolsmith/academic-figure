#!/usr/bin/env python3
"""Build the human-facing 180-case gallery from the public case index."""

from __future__ import annotations

import argparse
import html
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "skills" / "academic-figure"
INDEX = SKILL_ROOT / "references" / "cases" / "case-index.jsonl"
OUTPUT = ROOT / "GALLERY.md"

CATEGORIES = [
    (
        "比较与估计",
        "comparison-estimation",
        "组间差异、效应量、置信区间与响应排序。",
        ["rf-0107", "rf-0164", "rf-0172"],
    ),
    (
        "分布与不确定性",
        "distribution-uncertainty",
        "原始观测、分布形态、误差、配对变化与不确定性。",
        ["rf-0104", "rf-0137", "rf-0173"],
    ),
    (
        "关系与模型",
        "relationships-models",
        "变量关系、回归拟合、非线性效应与模型诊断。",
        ["rf-0100", "rf-0133", "rf-0180"],
    ),
    (
        "矩阵与模式",
        "matrices-patterns",
        "高维矩阵、相关结构、热图、排名与多层注释。",
        ["rf-0049", "rf-0063", "rf-0109"],
    ),
    (
        "组成与集合",
        "composition-sets",
        "比例构成、集合交并、多成分约束与组间组成变化。",
        ["rf-0001", "rf-0157", "rf-0162"],
    ),
    (
        "网络与流向",
        "networks-flows",
        "节点连接、模块结构、传播路径与流量变化。",
        ["rf-0043", "rf-0044", "rf-0118"],
    ),
    (
        "空间与层级",
        "spatial-hierarchy",
        "地理分布、空间分区、嵌套结构与层级关系。",
        ["rf-0055", "rf-0066", "rf-0122"],
    ),
    (
        "时间与过程",
        "time-process",
        "生存、时间序列、事件轨迹与个体过程。",
        ["rf-0018", "rf-0026", "rf-0061"],
    ),
    (
        "降维与聚类",
        "embedding-clustering",
        "低维嵌入、群落差异、聚类结果与模块注释。",
        ["rf-0041", "rf-0054", "rf-0091"],
    ),
]


def load_rows() -> list[dict]:
    rows = [
        json.loads(line)
        for line in INDEX.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 180, f"expected 180 cases, found {len(rows)}"
    return sorted(rows, key=lambda row: row["number"])


def target(row: dict) -> str:
    if row["releaseTier"] == "open-template":
        return f"skills/academic-figure/{row['templatePath']}/README.md"
    return f"skills/academic-figure/assets/case-atlas/{row['slug']}/"


def preview(row: dict) -> str:
    return f"skills/academic-figure/{row['previews'][0]['asset']}"


def safe_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def build_gallery(rows: list[dict]) -> str:
    by_id = {row["id"]: row for row in rows}
    by_category: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_category[row["category"]].append(row)

    known_categories = {name for name, *_ in CATEGORIES}
    assert set(by_category) == known_categories

    lines = [
        "# 科研图形图鉴",
        "",
        "这里收录 **180 个可检索科研图形案例**。图鉴用于识别信息结构、比较表达方案和定位可复用模板，不是要求用户机械复刻固定版式。",
        "",
        "- **开放模板**：包含案例中立化的 Python/R 双实现、演示数据和运行说明。",
        "- **图鉴案例**：开放缩略图、检索元数据和通用提示词，不包含对应案例的完整源码。",
        "- 图片仅用于结构参考；不得照搬案例中的名称、数值、阈值或统计结论。",
        "- 分类代表图来自图鉴；开放模板是案例中立化实现，不承诺与图鉴逐像素相同。",
        "",
        "[返回项目首页](README.md) · [查看 23 个开放模板](#open-templates) · [了解资产边界](CASE_ASSETS.md)",
        "",
        "## 按表达目标浏览",
        "",
        "| 表达目标 | 案例数 | 开放模板 | 适合回答的问题 |",
        "|---|---:|---:|---|",
    ]

    for name, anchor, description, _ in CATEGORIES:
        items = by_category[name]
        open_count = sum(item["releaseTier"] == "open-template" for item in items)
        lines.append(
            f"| [{name}](#{anchor}) | {len(items)} | {open_count} | {description} |"
        )

    lines.extend(
        [
            "",
            "> 页面只加载每类 3 张代表图；全部 180 条案例以可展开文字索引呈现。这样保留浏览广度，同时避免一次加载 180 张图片。",
            "",
            '<a id="open-templates"></a>',
            "## 23 个开放模板",
            "",
            "这些案例提供案例中立化的 Python/R 双实现、演示数据、运行说明和双版本预览。",
            "",
            "<details>",
            "<summary><strong>展开开放模板清单</strong></summary>",
            "",
            "| No. | 表达目标 | 开放模板 |",
            "|---|---|---|",
        ]
    )

    for item in (row for row in rows if row["releaseTier"] == "open-template"):
        href = target(item)
        lines.append(
            f"| [`{item['id']}`]({href}) | {item['category']} | "
            f"[{safe_cell(item['title'])}]({href}) |"
        )

    lines.extend(["", "</details>", ""])

    for name, anchor, description, featured_ids in CATEGORIES:
        items = by_category[name]
        open_count = sum(item["releaseTier"] == "open-template" for item in items)
        featured = [by_id[case_id] for case_id in featured_ids]
        assert all(item["category"] == name for item in featured)

        lines.extend(
            [
                f'<a id="{anchor}"></a>',
                f"## {name}",
                "",
                f"{description.rstrip('。')}，共 **{len(items)}** 个案例，其中 **{open_count}** 个开放模板。",
                "",
                '<table role="presentation">',
                "  <tr>",
            ]
        )

        for item in featured:
            lines.append(
                '    <td width="33%"><a href="{}"><img src="{}" alt="{}"></a></td>'.format(
                    target(item),
                    preview(item),
                    html.escape(f"{item['id']} {item['title']} 图鉴预览", quote=True),
                )
            )

        lines.extend(["  </tr>", "  <tr>"])
        for item in featured:
            status = "开放模板" if item["releaseTier"] == "open-template" else "图鉴案例"
            lines.append(
                "    <td><code>{}</code><br><strong>{}</strong><br><sub>{}</sub></td>".format(
                    item["id"], html.escape(item["title"]), status
                )
            )
        lines.extend(
            [
                "  </tr>",
                "</table>",
                "",
                "<details>",
                f"<summary><strong>查看“{name}”全部 {len(items)} 个案例</strong></summary>",
                "",
                "| 案例 | 图形类型 | 开放状态 |",
                "|---|---|---|",
            ]
        )

        for item in items:
            status = "**Python/R 模板**" if item["releaseTier"] == "open-template" else "图鉴案例"
            chart_types = "、".join(item["chartTypes"]) or "综合图形"
            href = target(item)
            lines.append(
                "| [`{}` · {}]({}) | {} | {} |".format(
                    item["id"],
                    safe_cell(item["title"]),
                    href,
                    safe_cell(chart_types),
                    status,
                )
            )

        lines.extend(["", "</details>", ""])

    lines.extend(
        [
            "## 如何使用图鉴",
            "",
            "1. 先明确研究问题、观察单位、变量角色和统计口径。",
            "2. 按表达目标选择类别，再用案例编号、标题或关键词缩小范围。",
            "3. 判断案例属于 `exact`、`structural`、`style-only` 还是需要新设计。",
            "4. 只有标记为“Python/R 模板”的案例包含开放实现；其余案例由 Skill 提取通用信息结构，不复制私有源码。",
            "",
            "本图鉴由 [公开案例索引](skills/academic-figure/references/cases/case-index.jsonl) 生成。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when GALLERY.md does not match the public case index",
    )
    args = parser.parse_args()

    content = build_gallery(load_rows())
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != content:
            raise SystemExit("GALLERY.md is stale; run .github/scripts/build_gallery.py")
        print("GALLERY.md is current")
        return 0

    OUTPUT.write_text(content, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
