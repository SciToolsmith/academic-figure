# rf-0018 supplied survival steps + risk table

预览：[Python 成图](../../assets/open-templates/rf-0018/preview-python.png) · [R 成图](../../assets/open-templates/rf-0018/preview-r.png)

该模板只绘制上游已经计算并明确提供的生存阶梯坐标、风险表和可选注释。它不接收个体事件数据，不拟合 Kaplan–Meier 曲线，不计算置信区间、删失标记或 log-rank 检验，也不把曲线分离解释为统计证据。

演示文件是中性模拟数据，固定种子 `18`，每行均标记 `SIMULATED`：

- `demo/demo_survival_steps_seed18.csv`：27 个 supplied step coordinates、3 条曲线。
- `demo/demo_risk_table_seed18.csv`：15 个 supplied risk counts。
- `demo/demo_annotations_seed18.csv`：3 个 supplied annotations。

## 依赖

- Python 3.9+ 与 Matplotlib。
- R 4.x，仅使用 base R、`graphics` 和 `grDevices`。

```bash
python3 -m pip install matplotlib
```

## 生存阶梯 CSV

必需字段：

| 字段 | 语义与约束 |
|---|---|
| `time` | 上游提供的阶梯坐标时间，有限数值且 `time >= 0`。 |
| `estimate` | 上游提供的生存估计，必须位于 `[0, 1]`。 |
| `curve_id` | 曲线 ID，不能为空。 |

同一 `curve_id` 的行必须在文件中按严格递增的 `time` 出现，不能有重复时间；脚本不会自动排序。每条曲线至少需要两个坐标，`estimate` 必须非递增。

使用 post-step 约定：某行 `estimate` 从该行 `time` 保持到下一条 supplied coordinate。脚本不在首坐标之前或末坐标之后外推，也不把坐标反推为个体事件或删失记录。

## 风险表 CSV

必需字段：

| 字段 | 语义与约束 |
|---|---|
| `time` | 风险表时间，必须落在相应 supplied curve 的时间范围内。 |
| `curve_id` | 必须已经存在于阶梯 CSV。 |
| `n_at_risk` | 上游提供的非负整数。 |

`curve_id + time` 必须唯一。每条曲线都必须使用相同、严格递增的风险表时间网格，便于逐列核对。脚本不会从阶梯坐标推算人数，也不会强制人数随时间递减，因为延迟进入等研究设计可能改变该模式。

## 可选 annotation CSV

字段为 `time,curve_id,label`。时间必须位于对应曲线范围内，`curve_id + time` 唯一，标签不能为空。注释 y 位置由 supplied post-step coordinate 定位；文字本身完全来自输入，不由脚本生成统计结论。

演示文件还包含 `data_status=SIMULATED` 和 `simulation_seed=18`。真实数据可以省略；若任一 supplied 文件声明模拟数据，则所有参与绘图的行必须声明相同固定种子。

## 运行

演示：

```bash
python3 python/plot.py --output-prefix output/survival_python
Rscript r/plot.R --output-prefix output/survival_r
```

真实数据：

```bash
python3 python/plot.py \
  --steps path/to/precomputed_steps.csv \
  --risk path/to/precomputed_risk.csv \
  --annotations path/to/supplied_annotations.csv \
  --output-prefix output/survival_python

Rscript r/plot.R \
  --steps path/to/precomputed_steps.csv \
  --risk path/to/precomputed_risk.csv \
  --annotations path/to/supplied_annotations.csv \
  --output-prefix output/survival_r
```

自定义输入必须同时给出 `--steps` 和 `--risk`；`--annotations` 可省略。该规则防止真实阶梯坐标意外混入演示风险表。Python 输出 PNG + SVG，R 输出 PNG + 单页 PDF。

## 解释边界

图题、副标题和图注均明确标识数据为 `SUPPLIED/PRECOMPUTED`。曲线高低、交叉或分离不能单独证明风险差异、比例风险、显著性或因果关系。若需要 KM、CI、log-rank 或模型估计，必须由具备个体级数据、研究设计和统计假设的上游分析完成，再将其结果按本契约提供。
