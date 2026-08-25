# 三元组成图开放模板

该模板用于展示三个非负组分在同一总和约束下的相对构成。Python/R 读取同一份长宽混合 CSV；图中的距离只表示组成差异，不自动表示统计显著性、相似性检验或机制。

## 数据契约

| 字段 | 必需 | 语义与校验 |
|---|---:|---|
| `sample_id` | 是 | 观察单位标识，全表唯一且非空 |
| `component_a`, `component_b`, `component_c` | 是 | 有限非负数；默认每行总和必须等于 `--sum-target` |
| `group` | 否 | 组别，默认 `All samples`；颜色与点型共同编码 |
| `facet` | 否 | 分面，默认 `Composition`；最多 9 个 |
| `label` | 否 | 仅对明确需要标注的样本填写；全图最多 18 个非空标签 |

未使用 `--normalize` 时，脚本严格检查三个组分之和，误差由 `--sum-tolerance` 控制。脚本不会因为一行“看起来像比例”就自动修正。

只在上游数据确实是同量纲的三部分非负数，且用户明确希望转换为行构成时，才使用 `--normalize`。此时每行除以该行原始总和，运行日志会明确记录已归一化；源 CSV 不会被改写。

## 演示数据

[`data/simulated_fixed_seed_demo.csv`](data/simulated_fixed_seed_demo.csv) 是固定种子 `162` 的中性模拟数据，每行显式标记 `source_type=simulated` 和 `source_seed=162`。组别、分面和构成数值只用于演示数据契约与布局，不代表真实科学结论。

## 预览

- [Python 成图](../../assets/open-templates/rf-0162/preview-python.png)
- [R 成图](../../assets/open-templates/rf-0162/preview-r.png)

## Python

依赖 Python 3.9+ 和 Matplotlib：

```bash
python3 python/plot.py \
  --input data/simulated_fixed_seed_demo.csv \
  --output-prefix output/ternary_python \
  --component-labels "Component A,Component B,Component C" \
  --title "Simulated three-part compositions"
```

输出 320 DPI PNG 和 SVG。

## R

依赖 R 4.2+，仅使用 base R：

```bash
Rscript r/plot.R \
  --input=data/simulated_fixed_seed_demo.csv \
  --output-prefix=output/ternary_r \
  --component-labels="Component A,Component B,Component C" \
  --title="Simulated three-part compositions"
```

输出 320 DPI PNG 和单页 PDF。

## 自适应与边界

- 1–9 个分面自动使用 1–3 列，全图保持同一组别编码。
- 最多 16 个组别；颜色不是唯一编码，同时使用点型。
- 网格只是组成坐标辅助线，不表示阈值、分类边界或显著区域。
- 本模板不计算组成距离、PERMANOVA、置信区域或中心点检验。如果需要推断，应使用与组成数据和研究设计相符的独立方法。
- 三个组分不构成同一闭合总和、含负值、有结构零或受检出限影响时，不应直接套用。
