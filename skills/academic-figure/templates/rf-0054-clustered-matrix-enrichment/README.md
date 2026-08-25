# 已排序矩阵、模块轨与上游注释模板

预览：[Python 成图](../../assets/open-templates/rf-0054/preview-python.png) · [R 成图](../../assets/open-templates/rf-0054/preview-r.png)

这个 Python/R 双实现模板展示一份已经在上游完成排序的数值矩阵，同时显示明确提供的模块轨、行条目注释和可选的上游富集注释。绘图脚本严格沿用元数据中的行序、列序和模块，不计算距离、不聚类、不重排，也不执行富集、通路查询、阈值筛选或功能命名。

## 输入契约

### 长矩阵

主 CSV 每行是一处矩阵单元：

| 字段 | 约束 |
|---|---|
| `row_id` | 必须出现在行元数据中 |
| `column_id` | 必须出现在列元数据中 |
| `value` | 有限数值，不允许缺失 |
| `value_scale` | 全图唯一、非空的数值尺度名称；用于颜色条 |

每个 `row_id + column_id` 必须唯一，并且必须完整覆盖行元数据与列元数据的笛卡尔积。缺失单元会终止运行；脚本不会补 0、插值或删除不完整条目。

### 行元数据

`--rows` CSV 必须包含：

| 字段 | 约束 |
|---|---|
| `row_id` | 非空且唯一 |
| `row_label` | 图中逐字显示的条目名称 |
| `row_order` | 从 1 开始、无重复、无缺口的明确行序 |
| `module` | 上游提供的模块 ID |
| `module_label` | 同一 module 内必须一致 |
| `module_order` | 从 1 开始、无重复、无缺口的模块序 |
| `row_annotation` | 可选列；非空时与 row label 一同显示，不作解释 |

同一模块必须在 `row_order` 中形成一个连续区块，区块顺序必须与 `module_order` 一致。脚本不会根据矩阵图案修正模块或顺序。

### 列元数据

`--columns` CSV 必须包含唯一的 `column_id`、非空 `column_label`，以及从 1 开始且无缺口的 `column_order`。

### 可选上游富集注释

`--annotations` CSV 使用 `module,annotation,annotation_value,annotation_order`。模块必须已声明，annotation 和 annotation_value 逐字显示；order 必须在每个模块内从 1 开始且无缺口。脚本不解析 P/FDR/NES 等含义、不应用阈值，也不会为没有注释的模块编造功能。

## 颜色尺度

运行时必须显式选择：

- `--color-mode diverging --color-center 0`：以指定中心构建对称色域；center 必须严格位于数据最小值和最大值之间。
- `--color-mode sequential`：按数据最小值到最大值使用连续色域，并且不得提供 center。

数值不会裁切。Python/R 都会记录实际色域。

## 演示数据

[`data/simulated_fixed_seed_matrix.csv`](data/simulated_fixed_seed_matrix.csv) 使用固定种子 `54` 生成 18×10 的中性矩阵；所有演示 CSV 都标注 `source_type=simulated`、`source_seed=54`。模块、条目文字和 [`data/supplied_enrichment_annotations.csv`](data/supplied_enrichment_annotations.csv) 仅用于演示契约，不代表真实聚类或富集结果。

## Python

依赖：Python 3.9+、NumPy 1.22+、Matplotlib 3.5+。

```bash
python3 python/plot.py \
  --matrix data/simulated_fixed_seed_matrix.csv \
  --rows data/row_metadata.csv \
  --columns data/column_metadata.csv \
  --annotations data/supplied_enrichment_annotations.csv \
  --color-mode diverging \
  --color-center 0 \
  --title "Simulated supplied matrix and modules" \
  --output-prefix output/matrix_python
```

输出 320 DPI PNG 和 SVG。

## R

依赖：R 4.2+；只使用 base R。

```bash
Rscript r/plot.R \
  --matrix data/simulated_fixed_seed_matrix.csv \
  --rows data/row_metadata.csv \
  --columns data/column_metadata.csv \
  --annotations data/supplied_enrichment_annotations.csv \
  --color-mode diverging \
  --color-center 0 \
  --title "Simulated supplied matrix and modules" \
  --output-prefix output/matrix_r
```

输出 320 DPI PNG 和 SVG。

## 可读性和科学边界

- 最多 60 行、40 列、12 个模块；每模块最多 4 条 supplied annotation，全图最多 30 条。超限明确停止，建议拆分或分页。
- 行标签和条目注释会自动换行，列标签按长度旋转；过多长文本仍可能需要人工缩写或分图，脚本不会静默截断。
- 发散色域保持关于 center 对称，因此当数据明显单侧时可能牺牲部分颜色分辨率；此时应显式改用 sequential，而不是移动中心迎合图案。
- 模板不能证明模块稳定性、聚类质量、富集有效性或生物学功能；这些必须来自可审查的上游分析。
