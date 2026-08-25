# Schema 驱动的基线特征表

这个 Python/R 双实现模板把“一行一个观察对象”的宽表汇总为按组排列的描述性基线表。变量类型和摘要口径必须由独立 schema 明确声明；脚本不会根据列名或取值猜测连续/分类类型，也不默认计算 P 值或标准化差异。

预览：[Python 成图](../../assets/open-templates/rf-0027/preview-python.png) · [R 成图](../../assets/open-templates/rf-0027/preview-r.png)

## 数据契约

主 CSV 必须包含：

| 字段 | 约束 |
|---|---|
| `id` | 非空且全表唯一；一行表示一个观察对象 |
| `group` | 非空分组；按首次出现顺序形成表格列 |
| schema 变量 | 空字符串表示缺失；非空值必须符合 schema 类型与水平 |

[`data/variable_schema.csv`](data/variable_schema.csv) 每行声明一个变量，列定义如下：

| 列 | 规则 |
|---|---|
| `variable` | 主 CSV 中的唯一列名，不得为 `id` 或 `group` |
| `label` | 表格显示名称 |
| `type` | `continuous` 或 `categorical` |
| `levels` | 分类变量必填，使用 `|` 分隔并定义显示顺序；连续变量留空 |
| `summary` | 连续变量为 `mean_sd` 或 `median_iqr`；分类变量固定为 `n_percent_nonmissing` |
| `decimals` | 0–6 的整数；控制连续摘要小数位 |

未在分类 levels 中声明的非空值会终止运行。主 CSV 的额外来源字段可以保留，但不参与汇总。

## 缺失与分母

- 每个变量标题行逐组显示 `available n/N; missing m`。
- 分类水平显示 `count/non-missing (percent)`；百分比的分母是该组、该变量的非缺失数，不是组总 N。
- 连续摘要排除该变量的缺失值；`mean_sd` 使用样本标准差，只有一个有效值时 SD 显示 `NA`。
- `median_iqr` 显示 `Median [Q1, Q3]`，四分位数采用线性插值（R type 7）。
- 不删除整行对象；标准输出记录输入对象数、缺失单元格及逐变量分母。

## 演示数据

[`data/simulated_fixed_seed_demo.csv`](data/simulated_fixed_seed_demo.csv) 使用固定种子 `27` 生成，并逐行标注 `source_type=simulated`、`source_seed=27`。它仅演示类型、缺失和动态组列，不代表真实基线结论。

## Python

依赖：Python 3.9+、NumPy 1.22+、Matplotlib 3.5+。

```bash
python3 python/plot.py \
  --input data/simulated_fixed_seed_demo.csv \
  --schema data/variable_schema.csv \
  --output-prefix output/baseline_python \
  --include-overall true \
  --title "Simulated baseline characteristics"
```

输出 `output/baseline_python.png`（320 DPI）与 `output/baseline_python.svg`。

## R

依赖：R 4.2+；只使用 base R。

```bash
Rscript r/plot.R \
  --input data/simulated_fixed_seed_demo.csv \
  --schema data/variable_schema.csv \
  --output-prefix output/baseline_r \
  --include-overall true \
  --title "Simulated baseline characteristics"
```

输出 `output/baseline_r.png`（320 DPI）与 `output/baseline_r.svg`。

## 边界

- 支持动态变量和组数，但最多显示 6 个组列（含可选 Overall）和 40 个展开行；超限时明确报错，建议按预定义主题拆表。
- `--include-overall true` 增加 Overall 列；若真实组名已为 `Overall` 会报冲突。
- 本模板只做描述性汇总，不计算 P 值、SMD、置信区间或缺失值插补。若需平衡诊断，必须另行定义变量尺度、权重、SMD 公式和适用总体。
- 不适合重复测量、层级对象或一行并非独立观察单位的数据，除非先按研究设计整理到正确分析单位。
