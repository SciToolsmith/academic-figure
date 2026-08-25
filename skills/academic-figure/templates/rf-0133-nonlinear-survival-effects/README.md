# 上游非线性效应曲线模板

预览：[Python 成图](../../assets/open-templates/rf-0133/preview-python.png) · [R 成图](../../assets/open-templates/rf-0133/preview-r.png)

这个 Python/R 双实现模板只负责展示上游分析已经计算好的“暴露—效应—区间”网格。它连接提供的网格点、绘制提供的区间，并标出提供的参考暴露和参考效应；不会拟合 Cox、限制性立方样条、GAM 或任何其他模型，也不计算 P 值、区间或显著性。

## 曲线数据契约

主 CSV 每行是某个分面和组别的一处上游网格点，必须包含：

| 字段 | 约束 |
|---|---|
| `facet` | 非空分面标识；按首次出现顺序布局 |
| `group` | 非空曲线组别；颜色和线型共同编码 |
| `exposure` | 有限数值；同一 `facet + group` 内唯一 |
| `effect` | 上游效应估计，必须位于对应区间内 |
| `ci_lower`, `ci_upper` | 上游提供的区间端点，且 `ci_lower <= effect <= ci_upper` |
| `reference_exposure` | 该曲线的参考暴露；必须对应一个实际提供的网格点 |
| `reference_effect` | 全图唯一的参考效应值；参考网格点的 effect 必须与其一致 |
| `exposure_label` | 含单位或尺度的 x 轴名称；全图唯一 |
| `effect_measure` | 明确的效应量名称，例如 `Hazard ratio` 或 `Risk difference`；全图唯一 |
| `effect_scale` | `ratio` 或 `difference`；全图唯一 |
| `interval_level` | 0–1 之间的区间水平，例如 `0.95`；全图唯一 |
| `interval_type` | 上游区间类型的非空名称，例如 `confidence` 或 `credible`；全图唯一 |

`ratio` 尺度要求 effect、区间端点和 reference effect 都严格大于 0。每条曲线至少需要 3 个网格点；脚本按数值 exposure 排序后连接相邻的已提供点，不平滑、不补点，也不会把区间带延伸到该曲线最小/最大 exposure 之外。参考点按 `--reference-tolerance` 校验，默认 `1e-6`。

## 可选 supplied annotation

`--annotations` 可接收另一份 CSV，字段为 `facet,group,x,y,label`。`group` 可留空表示分面级注释，其余字段必须非空；坐标必须落在该分面已提供的 exposure 和区间范围内。文字逐字显示，不解析显著性、不生成统计结论。每分面最多 12 条、单条最多 90 个字符。

## 演示数据

[`data/simulated_fixed_seed_demo.csv`](data/simulated_fixed_seed_demo.csv) 使用固定种子 `133` 生成中性 ratio-scale 曲线，并逐行标注 `source_type=simulated`、`source_seed=133`。可选的 [`data/supplied_annotations.csv`](data/supplied_annotations.csv) 也是演示性上游注释，不代表真实结果。

## Python

依赖：Python 3.9+、NumPy 1.22+、Matplotlib 3.5+。

```bash
python3 python/plot.py \
  --input data/simulated_fixed_seed_demo.csv \
  --annotations data/supplied_annotations.csv \
  --y-transform linear \
  --title "Simulated upstream effect curves" \
  --output-prefix output/effect_curves_python
```

输出 320 DPI PNG 和 SVG。

## R

依赖：R 4.2+；只使用 base R。

```bash
Rscript r/plot.R \
  --input data/simulated_fixed_seed_demo.csv \
  --annotations data/supplied_annotations.csv \
  --y-transform linear \
  --title "Simulated upstream effect curves" \
  --output-prefix output/effect_curves_r
```

输出 320 DPI PNG 和 SVG。

## 适用与边界

- 适用于已经完成模型拟合、参考值定义和区间计算，只需要审慎展示上游输出的场景。
- `--y-transform log` 只允许用于 `ratio` 尺度且全部区间严格为正；脚本不会因为 effect 看起来像比值而自动改成对数轴。
- 最多 9 个分面、8 个全局组别、每条曲线 500 个点；超限明确停止，建议拆图。
- 模板不会验证上游模型、删失处理、比例风险假设、样条自由度、协变量调整、区间计算或因果解释；这些仍须由分析者确认。
- 不适合只有个体级生存时间/结局、而没有上游效应曲线与区间的数据；此模板不会代替统计分析。
