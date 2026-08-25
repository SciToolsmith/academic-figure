# rf-0107 supplied feature + precomputed enrichment template

预览：[Python 成图](../../assets/open-templates/rf-0107/preview-python.png) · [R 成图](../../assets/open-templates/rf-0107/preview-r.png)

该模板只负责组合展示上游提供的 feature-level effect/significance，以及预计算的 ranked enrichment curve、hit positions 和 summary。它不会运行 GSEA 或其他富集算法，不查询或补充通路，不生成排名，不重新计算 P 值或多重校正，也不把可视化结果背书为富集结论。

中性演示数据固定随机种子为 `107`，每行均标记 `SIMULATED`：

- `demo/demo_features_seed107.csv`：120 个 supplied feature statistics 和上游提供的显示分类。
- `demo/demo_ranked_curves_seed107.csv`：2 条曲线、202 个 precomputed coordinates。
- `demo/demo_hits_seed107.csv`：28 个 supplied hit positions。
- `demo/demo_summary_seed107.csv`：2 行 supplied summary。

## 依赖

- Python 3.9+ 与 Matplotlib。
- R 4.x，仅使用 base R、`graphics` 和 `grDevices`。

```bash
python3 -m pip install matplotlib
```

## Feature-level CSV

必需字段：

| 字段 | 语义与约束 |
|---|---|
| `feature` | 唯一 feature ID，不能为空。 |
| `effect` | 上游提供的有限数值效应。模板不改变方向或单位。 |
| `significance` | 上游提供的 `(0, 1]` 尾概率型显示量；图中仅做 `-log10` 显示变换。 |
| `significance_class` | 可选显示分类。若使用，必须为每一行提供；脚本按原文着色，不重新判定。 |

`significance` 的统计口径必须由上游说明，例如 nominal P、adjusted P 或其他已限定量。该通用字段不会自动改名为 P/FDR，也不会证明其校正方法正确。

### 显式阈值分类

若 CSV 未提供 `significance_class`，默认所有点为 `Unclassified`。只有用户同时显式传入以下两个参数，脚本才生成显示分类和参考线：

```text
--effect-threshold <positive number>
--significance-threshold <number in (0, 1]>
```

生成规则为 supplied significance 不大于阈值，且 effect 分别大于正阈值或小于负阈值；其余为 other。阈值分类只控制图形编码，不产生统计结论。输入已经含分类时禁止再传阈值，避免双重口径。

## Precomputed curve CSV

字段为 `curve_id,rank,running_score`：

- `curve_id` 不能为空；单图最多 8 条曲线。
- `rank` 必须是正整数，并在每条曲线中按文件顺序严格递增；脚本不自动排序。
- `running_score` 必须是有限数值，按原值连线。

脚本不会从 feature 表生成 rank 或 running score，也不会搜索、平滑或重新归一化曲线。

## Hit CSV

字段为 `curve_id,rank`。`curve_id` 必须存在于 curve CSV；rank 必须精确对应一条 supplied curve coordinate；组合必须唯一。Hit 只作为 supplied rug marks 显示，不参与重新计算曲线。

## Summary CSV

每条曲线恰好一行：

| 字段 | 必需 | 约束 |
|---|---:|---|
| `curve_id` | 是 | 必须存在于 curve CSV。 |
| `enrichment_score` | 是 | 上游提供的有限数值，仅显示。 |
| `p_value` | 否 | `[0, 1]`；按供应值显示。 |
| `adjusted_p_value` | 否 | `[0, 1]`；不由模板计算。 |
| `hit_count` | 否 | 正整数；若同时提供 hit CSV，必须与其条数一致。 |

这些名称是传输字段，不证明上游方法属于某一种 GSEA 实现或满足其假设。

演示文件均包含 `data_status=SIMULATED` 和 `simulation_seed=107`。真实数据可以省略；若任一参与文件声明模拟数据，则所有参与绘图的行必须声明同一固定种子。

## 自适应面板与运行

没有指定数据参数时运行完整演示：

```bash
python3 python/plot.py --output-prefix output/feature_enrichment_python
Rscript r/plot.R --output-prefix output/feature_enrichment_r
```

自定义数据可只提供 feature 面板、只提供 enrichment 面板，或同时提供：

```bash
python3 python/plot.py \
  --features path/to/supplied_features.csv \
  --curve path/to/precomputed_curve.csv \
  --hits path/to/supplied_hits.csv \
  --summary path/to/supplied_summary.csv \
  --output-prefix output/custom_python

Rscript r/plot.R \
  --features path/to/supplied_features.csv \
  --curve path/to/precomputed_curve.csv \
  --hits path/to/supplied_hits.csv \
  --summary path/to/supplied_summary.csv \
  --output-prefix output/custom_r
```

`--hits` 和 `--summary` 必须与 `--curve` 一起使用。只要传入任一自定义文件，脚本就不会自动混入其他演示文件。Python 输出 PNG + SVG，R 输出 PNG + 单页 PDF。

## 解释边界

每个图内标题和图注均明确标识 `supplied/precomputed`。模板只能验证字段、范围、排序、主键、hit 对应关系和可选 summary 一致性，不能验证 feature universe、排名构造、通路来源、置换策略、相关结构、多重检验或富集结果的统计有效性。
