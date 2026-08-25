# rf-0157 通用 UpSet 模板

该模板从 `item + set` 成员关系长表精确计算集合大小和互斥的成员组合，并绘制标准 UpSet 矩阵。它不把集合关系改画成 Venn 图，也不依赖手写交集数或人工判断组合。

演示数据使用固定随机种子 `157`，并在每行明确标记 `SIMULATED`：

- `demo/demo_membership_seed157.csv`：120 个中性 item、223 条唯一成员关系。
- `demo/demo_set_spec.csv`：7 个允许的集合及其显示顺序。

预览：[Python 成图](../../assets/open-templates/rf-0157/preview-python.png) · [R 成图](../../assets/open-templates/rf-0157/preview-r.png)

## 依赖

- Python 3.9+ 与 Matplotlib。
- R 4.x，仅使用 base R、`graphics` 和 `grDevices`。

```bash
python3 -m pip install matplotlib
```

## 成员关系长表

| 字段 | 必需 | 语义与约束 |
|---|---:|---|
| `item` | 是 | 项目、对象或事件的唯一 ID，不能为空。 |
| `set` | 是 | 该 item 所属集合的 ID，必须在 set spec 中声明。 |

同一 item 属于多个集合时写多行。每个 `item + set` 组合必须唯一；重复行会被拒绝而不是静默去重。空 item、空 set、未知集合均为错误。

演示表还包含 `data_status=SIMULATED` 和 `simulation_seed=157`。真实数据可以省略；声明模拟数据时，每行必须使用同一个正整数种子。

该长表的 item 宇宙定义为至少有一个成员关系的 item 并集。因此零集合成员的 item 无法在此契约中表达；若它们属于研究总体，应在进入模板前单独报告，不能伪造“空集合”成员行。

## Set spec

`demo_set_spec.csv` 包含：

| 字段 | 语义与约束 |
|---|---|
| `set` | 唯一集合 ID，也是 membership 表的允许值。 |
| `label` | 唯一且非空的显示名称。 |

集合和矩阵行按 spec 首次出现顺序排列。每个已声明集合必须至少有一个 item；空集合会被明确拒绝。

## 精确计数定义

- 集合大小：membership 表中属于该集合的唯一 item 数。
- 精确交集：具有完全相同集合成员模式的 item 数。每个 item 恰好进入一个精确交集。
- 精确交集不是 inclusive overlap。例如 `{A, B}` 柱不包含同时属于 `{A, B, C}` 的 item。

图中顶部柱由脚本直接从成员关系计算；不得输入或覆盖手写交集数。

## Top intersection 规则

`--top N` 最多显示前 N 个非零精确交集，默认 `12`。完整稳定排序为：

1. 精确交集大小降序；
2. 组合 degree，即所含集合数降序；
3. 按 set spec 顺序形成的集合索引元组升序。

图注和终端都会报告非零精确交集总数、显示数及未显示数。未显示只影响可视化，不影响集合大小或总交集计数。`--top` 允许 `1–50`，不使用隐式最小计数阈值。

## 运行

Python：

```bash
python3 python/plot.py \
  --input demo/demo_membership_seed157.csv \
  --set-spec demo/demo_set_spec.csv \
  --output-prefix output/upset_python \
  --top 12 \
  --dpi 320
```

R：

```bash
Rscript r/plot.R \
  --input demo/demo_membership_seed157.csv \
  --set-spec demo/demo_set_spec.csv \
  --output-prefix output/upset_r \
  --top 12 \
  --dpi 320
```

Python 生成 PNG + SVG；R 生成 PNG + 单页 PDF。默认输入根据脚本位置推导，默认输出位于运行命令的当前目录，不包含机器相关绝对路径。

## 动态布局与边界

画布宽度随显示交集数变化，高度随集合数变化。为保持矩阵可读性，单图允许 2–16 个集合；超过 16 个时明确停止并要求按科学问题拆成可解释的集合族。集合数较少时仍使用 UpSet 的精确成员矩阵，不退化为 Venn 图。

模板验证集合成员关系和精确组合计数的一致性，但不能判断 item ID 是否在上游被错误合并、集合定义是否可比较，或 top 组合是否足以回答特定研究问题。
