# Precomputed ordination 通用模板

这是 `rf-0091` 的去案例化 Python/R 双实现。模板只接收上游已经计算好的二维 ordination 坐标，绘制主散点和按组的轴向箱线分布；不在绘图脚本中实现 PCoA、PCA、NMDS、PERMANOVA 或其他降维/检验算法。

## 数据契约

### 坐标表

UTF-8 CSV 一行一个 sample：

| 字段 | 要求 |
|---|---|
| `sample_id` | 必需、非空、全表唯一 |
| `axis1`, `axis2` | 必需、有限数值；不接受空值、`NA`、`Inf` 或 `NaN` |
| 可选 group | 通过 `--group-column` 显式指定；若指定，每行必须非空，最多 12 个水平，每组至少 2 个 sample |

每条轴在当前输入中都必须有变异。额外列不参与绘图。演示表 `data/simulated_fixed_seed_ordination.csv` 含 60 个中性对象和 3 个无领域含义的组别，由固定伪随机种子 `91` 生成；每行以 `data_status=SIMULATED`、`simulation_seed=91` 标记。

### 可选轴元数据

`--axis-metadata` 指向包含以下字段的 CSV：

- `axis_key`: 必须且只能各出现一次 `axis1`、`axis2`。
- `axis_label`: 非空显示标签。
- `explained_variance`: 有限的 0–1 比例；两轴之和不得超过 1。脚本将其格式化为百分比，但不重新估计或验证该解释率的统计来源。

省略时使用 `Axis 1`、`Axis 2`，不显示解释率。演示文件为 `data/simulated_fixed_seed_axis_metadata.csv`。

### 可选来源检验注释

`--supplied-annotations` 指向包含 `annotation_id`、`annotation_text`、`source_label` 的 CSV。ID 必须唯一，文本和来源必须非空；最多 3 条、每条最多 300 字符。图中每条都以前缀 `SUPPLIED —` 显示。

绘图脚本把注释作为来源提供的文本原样排版，不解析、计算、复核或背书其中的统计量和结论。演示文件 `data/simulated_fixed_seed_supplied_annotations.csv` 中的数字同样只是种子 91 的模拟文本，不是真实检验结果。

若任一输入表包含 provenance 字段，则 `data_status` 与 `simulation_seed` 必须成对出现、表内一致；多个已声明 provenance 的表之间也必须一致。

预览：[Python 成图](../../assets/open-templates/rf-0091/preview-python.png) · [R 成图](../../assets/open-templates/rf-0091/preview-r.png)

## 运行

Python 3.9+ 依赖 `numpy` 和 `matplotlib`：

```bash
python3 python/plot.py \
  --input data/simulated_fixed_seed_ordination.csv \
  --group-column group \
  --axis-metadata data/simulated_fixed_seed_axis_metadata.csv \
  --supplied-annotations data/simulated_fixed_seed_supplied_annotations.csv \
  --output-prefix /path/to/output/ordination_python \
  --title "Simulated precomputed ordination" \
  --dpi 320
```

输出 PNG 与 SVG。

R 4.2+ 只使用 base R：

```bash
Rscript r/plot.R \
  --input=data/simulated_fixed_seed_ordination.csv \
  --group-column=group \
  --axis-metadata=data/simulated_fixed_seed_axis_metadata.csv \
  --supplied-annotations=data/simulated_fixed_seed_supplied_annotations.csv \
  --output-prefix=/path/to/output/ordination_r \
  --title="Simulated precomputed ordination" \
  --dpi=320
```

输出 PNG 与 PDF。省略 `--group-column` 时，边缘面板显示总体分布；省略两个可选文件时，不补造解释率或检验注释。

## 自适应布局与解释边界

画布随组数、组标签长度、轴标签和 supplied 注释行数增长；组别同时使用颜色与形状。主图的两轴使用相同物理尺度，边缘面板保持与主图相同的坐标范围。

点云接近、分离、方向或边缘箱线差异都只是已提供坐标的描述。模板不能声称它计算或验证了 ordination、解释率或任何来源检验；预处理、距离度量、降维算法、随机种子、批次结构和推断设计必须由上游分析及图注说明。
