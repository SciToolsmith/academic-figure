# 公开案例图鉴

该目录是 Skill 的检索资源，不是 180 个完整源码的打包。

## 内容

- `case-index.jsonl`：180 个案例的元数据、科学任务线索、数据结构线索、缩略图路径和开放实现状态。
- `case-prompts.json`：180 个案例的 Python/R 通用绘图提示词。只在选中案例后读取对应条目。
- `open-template-roadmap.json`：首发开放模板注册表，记录每个案例的波次、双语实现、公开路径和验证日期。
- `../../assets/case-atlas/`：案例缩略图，按 slug 分目录存放。
- `../../assets/open-templates/`：实际跑通的开放模板双语预览。
- `../../templates/`：只包含已去案例化并通过对应语言运行验证的开放实现。

## 关键字段

- `researchGoals`：粗粒度证据任务。
- `dataShapes`：典型数据结构，仅作检索线索，不代替字段验证。
- `relationshipHints`：配对、时间、层级、网络等关系线索。
- `previews`：缩略图路径与原始成图宽高。
- `releaseTier`：`atlas` 表示图鉴层；`open-template` 表示已有去案例化开放模板。
- `openImplementation`：按 Python/R 单独声明实际开放状态。
- `templatePath`：仅对实际开放的案例提供，值为 Skill 根目录下的相对路径。

`promptStatus` 是内容编辑状态，不是对科学正确性、运行成功或期刊接收的保证。

当前首发状态：180 个图鉴案例中，23 个为经过双语运行验证的 `open-template`，其余 157 个仅保留为 `atlas` 检索资源。图鉴公开不等于对应私有案例源码公开。

## 检索

```bash
python scripts/search_cases.py "研究问题 数据结构 变量关系" --limit 5
python scripts/search_cases.py "rf-0156" --language r --include-prompt --json
python scripts/search_cases.py "置信区间 效应" --open-only --language r --limit 5
```

检索结果为零时，先换用更接近证据任务和数据结构的描述；仍无匹配时，进入新建图形路线。
