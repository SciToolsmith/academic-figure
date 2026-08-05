# SciPlot｜科研绘图

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

SciPlot 是一个面向 Codex 的科研绘图 Agent Skill。它把论文图件视为一条可审计的视觉论证链：

`科学问题或主张 → 证据 → 面板角色 → 视觉编码 → 导出图件`

它可以帮助智能体创建、修改或审查论文级科研图件，同时优先保护数据含义、统计语义、可复现性和导出质量。

> SciPlot 是独立的社区项目，与 Nature、Springer Nature 或任何期刊没有隶属或官方合作关系。“Nature-style”在本项目中仅表示克制、证据导向的出版级设计。

## 安装

### 方式一：让 Codex 安装

在 Codex 中输入：

```text
请使用 $skill-installer 安装：
https://github.com/HailCodeMaster/sci-plot/tree/main/skills/sci-plot
```

安装后可用 `$sci-plot` 显式调用。Codex 通常会自动检测新 skill；如果没有出现，请重启 Codex。

### 方式二：手动安装到用户范围

```bash
git clone https://github.com/HailCodeMaster/sci-plot.git
mkdir -p "$HOME/.agents/skills"
cp -R sci-plot/skills/sci-plot "$HOME/.agents/skills/sci-plot"
```

Codex 当前也支持把 skill 放在项目的 `.agents/skills/` 下，使其只在该仓库范围内生效。参见 OpenAI 的 [Build skills](https://developers.openai.com/plugins/build/skills) 文档。

## 快速使用

创建图件：

```text
$sci-plot 根据这份数据和研究问题设计一张论文主图，输出可编辑 SVG、预览图、Figure Contract 和 QA 结果。
```

修改图件：

```text
$sci-plot 在不改变统计含义的前提下重构这个多面板图，并记录前后差异。
```

审查图件：

```text
$sci-plot 审查这张图的数据完整性、统计语义、视觉诚实性、可读性和导出质量；先不要修改文件。
```

## 核心设计

- **先定义证据，再选择图形**：先明确科学问题、分析单位、重复单位、主张和面板角色。
- **Figure Contract**：在绘制前固定数据语义、统计表达、面板职责和目标输出。
- **案例是可选设计先验**：18 个正向案例帮助检索科学表达决策，但不是模板库或能力边界。
- **允许没有合适案例**：检索不到语义匹配时返回 `build-new`，继续按图形语法原创设计。
- **风险卡优先暴露错误**：6 张风险卡覆盖视觉误导、错误聚合、数据泄漏、统计注释失真等问题。
- **保护数据与统计含义**：记录过滤、变换、聚合、缺失值、样本量、不确定性和多重比较。
- **真实渲染后验收**：分别检查代码、运行、文件、视觉和科学有效性；任何一项都不能替代其他项。
- **后端中立**：可根据任务选择 Python、R 或混合工作流，并保留面板级来源信息。

## 案例如何使用

案例展示的是“为什么这样表达证据”，而不只是某种外观。每次任务默认只选一个主案例和至多一个辅助案例，并明确采用以下一种复用等级：

1. 精确复用：科学语义、数据维度、变换和输入契约均兼容。
2. 结构适配：复用证据逻辑，重新映射字段、单位、顺序和重复单位。
3. 仅继承风格：只借用视觉语言，不迁移统计逻辑。
4. 重新设计：问题、结构或推断假设不兼容时从零设计。

仓库中的案例预览由项目作者独立编码复现，用于内部化科学表达决策；它们不是论文原图、论文附带代码或原始数据。
更完整的公开边界见 [CASE_ASSETS.md](CASE_ASSETS.md)。

## 仓库结构

```text
skills/sci-plot/
├── SKILL.md
├── agents/openai.yaml
├── assets/cases/
├── references/
└── scripts/
```

- `SKILL.md`：主工作流、触发范围和交付要求。
- `references/`：Figure Contract、图形语法、数据完整性、QA、案例卡和风险卡。
- `scripts/rank_cases.py`：按科学语义检索候选案例，允许无匹配结果。
- `scripts/validate_contract.py`：检查序列化 Figure Contract 的关键约束。
- `assets/cases/`：经过筛选的案例预览。

## 本地验证

```bash
python3 skills/sci-plot/scripts/rank_cases.py --validate-only
python3 skills/sci-plot/scripts/validate_contract.py \
  skills/sci-plot/references/figure-contract.example.json \
  --pretty
```

预期结果分别包含 `valid: 18 cases` 和 `PASS`。

## 许可与边界

本项目以 [Apache-2.0](LICENSE) 发布；许可文本同时保留在仓库根目录和可安装的 skill 目录中。生成的图形、引用、统计结论和实验描述仍须由研究者核验。

---

## English

SciPlot is a Codex Agent Skill for designing, revising, and auditing publication-ready scientific figures. It treats cases as optional design priors rather than templates or capability limits, and it can continue with a principle-first `build-new` workflow when no suitable case exists.

To install, ask Codex:

```text
Use $skill-installer to install:
https://github.com/HailCodeMaster/sci-plot/tree/main/skills/sci-plot
```

Then invoke it explicitly with `$sci-plot`.
