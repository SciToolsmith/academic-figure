---
name: academic-figure
description: >-
  Improve the scientific expression, visual quality, and reproducibility of data-driven research figures in Python or R without changing their scientific meaning. Use when a user asks to improve a paper figure, choose a more suitable visualization from a research question or dataset, match a reference figure to a better chart structure, write publication-oriented plotting code, or audit figure clarity, uncertainty, layout, color, typography, and export quality. Also use for 科研绘图、论文配图、学术图形、科研图形优化、图形审校、可视化重构、图形推荐、Python/R 绘图代码 and publication-ready figure workflows. Do not use for statistics-only analysis, interactive dashboards, decorative infographics, or mechanism diagrams whose primary content is illustration rather than data.
---

# 科研图形优化

目标：在保持科学含义、不越过证据边界的前提下，提升科研图形的科学表达、视觉质量与可复现性；必要时，推荐与数据和研究问题更匹配的表达方式。

本 Skill 是路由器，不是长提示词。每次调用先读 [manifest.yaml](manifest.yaml)，再读其 `always_load` 中的核心文件。只按任务需要加载深层参考，不要一次性读取全部案例和提示词。

## 1. 判断任务路由

- **审校**：已有图形或代码，需要找出科学表达、视觉层级、可读性或交付问题。读 [references/figure-review.md](references/figure-review.md)。
- **选图**：用户有研究问题、数据或参考图，但不确定哪种表达更合适。读 [references/figure-selection.md](references/figure-selection.md)。
- **重构**：需要生成或修改 Python/R 代码、成图和输出。读 [references/asset-adaptation.md](references/asset-adaptation.md)。
- **交付**：只要生成或修改了图形，交付前读 [references/delivery-qa.md](references/delivery-qa.md)。

只有一张图时仍可审校视觉表达并推荐候选结构，但不得声称已验证原始数据、统计方法或结论。

## 2. 先建立简短图形契约

绘图前确认：

1. 一句话研究问题或图形要支持的信息。
2. 观察单位、分组/配对/重复测量关系。
3. 关键变量的含义、尺度、单位和变换。
4. 要展示的原始值、效应、不确定性、模型输出或关系结构。
5. 目标读者、最终尺寸和输出格式。

只在缺失信息会改变科学含义、图形家族或统计表达时追问；一次最多 3 个具体问题。

## 3. 检索案例，不凭外观硬套

将“研究目标 + 数据结构 + 变量关系 + 图形线索”组成查询：

```bash
python scripts/search_cases.py "配对对象 两个时点 显示个体变化与不确定性" --limit 5
```

1. 先看前 5 个结果元数据，再只打开最相关的 1–3 张缩略图。
2. 先选科学与结构匹配的案例，再比较视觉风格。
3. 确定候选案例后，才读对应语言提示词：

```bash
python scripts/search_cases.py "rf-0156" --limit 1 --language python --include-prompt --json
```

4. 不要整体加载 `case-prompts.json`。案例是结构和设计证据，不代替对用户数据的判断。

若检索结果同时给出 `templatePath`，且 `openImplementation` 中目标语言为 `true`，先读该模板的 `README.md`，再只打开目标语言脚本。没有这两个条件时，不得把图鉴案例称为开放源码模板。

## 4. 决定复用深度

参照 [references/asset-adaptation.md](references/asset-adaptation.md) 明确选择：

- `exact`：数据契约与证据任务高度一致，只替换数据映射和参数。
- `structural`：保留信息架构，根据新数据改面板数量、布局和编码。
- `style-only`：只借用配色、层级、留白、字体和标注原则。
- `new`：案例不匹配时重新设计，不为了“像”而牺牲科学合理性。

布局必须随数据自适应。参考案例是 3×2，不代表用户数据也应生成 3×2；可改为单图、1×2、2×1、分页或多张输出。

## 5. 解析语言并执行

- 用户指定 Python/R，或提供了明确语言的代码：沿用该语言。
- 只要审校或选图：不必先问语言。
- 要生成代码但语言不明：说明技术路线；若两者都合适，只问一个简短问题。

确定后只加载一份语言片段：

- Python：[static/fragments/backend/python.md](static/fragments/backend/python.md)
- R：[static/fragments/backend/r.md](static/fragments/backend/r.md)

有真实数据时必须使用真实数据，不得用模拟数据替换。没有数据且用户希望看可运行演示时，可用明确标注、固定随机种子的中性模拟数据；不得将其解读为真实结论，也不得在真实数据读取失败后静默切换。

## 6. 交付最小完整包

生成或修改图形时，默认交付：

1. 选图与布局理由。
2. 字段映射、统计口径和数据排除记录。
3. 完整、可运行的选定语言脚本，依赖与运行命令。
4. PDF/SVG 之一，以及适用时的 300 DPI 以上 PNG/TIFF。
5. 最终尺寸下的视觉检查和仍需人工确认的科学风险。

只审校或选图时，不要为了显得完整而擅自写代码、改数据或生成新图。
