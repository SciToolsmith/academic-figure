# Relationship matrix 通用模板

这是 `rf-0049` 的去案例化 Python/R 双实现。输入是一行一个 sample、多个显式选择的连续变量，以及可选分组。对角线显示单变量分布，下三角显示散点，上三角显示描述性相关系数和该变量对实际使用的 `n`。

模板不计算 P 值、置信区间、多重检验校正或因果效应，也不据相关强弱生成显著性或机制结论。

## 数据契约

单张 UTF-8 CSV 至少包含：

| 字段 | 要求 |
|---|---|
| `sample_id` | 必需、非空、全表唯一；重复 ID 会终止绘图 |
| 连续变量 | 通过 `--variables` 逐一显式指定；每个非缺失值必须是有限数值 |
| 可选 group | 通过 `--group-column` 指定；若指定，每行必须非空，最多 12 个水平 |

缺失值只接受空单元格或精确字符串 `NA`。其他非数值文本、`Inf`/`NaN` 不会被静默转成缺失。未列入 `--variables` 的额外列不参与分析。

演示表 `data/simulated_fixed_seed_relationships.csv` 含 48 个中性对象、5 个连续变量和 3 个无领域含义的组别。它由固定伪随机种子 `49` 生成，并在每行以 `data_status=SIMULATED`、`simulation_seed=49` 标记；少量预设空值用于演示缺失策略。

预览：[Python 成图](../../assets/open-templates/rf-0049/preview-python.png) · [R 成图](../../assets/open-templates/rf-0049/preview-r.png)

## 必须显式选择的统计语义

- `--correlation-method pearson`：描述性 Pearson 线性相关。
- `--correlation-method spearman`：描述性 Spearman 秩相关；并列值使用平均秩。
- `--missing-policy pairwise`：每个对角分布使用该变量的可用值；每个散点/相关单元使用该变量对的完整观测。上三角逐格报告实际 `n`。
- `--missing-policy complete`：先保留所有所选变量均完整的行，再由同一批行绘制全部单元。运行日志报告保留行数。

脚本不提供隐式默认：相关方法与缺失策略都必须在命令中写明。任一变量或变量对少于 3 个可用观测、在对应观测中无变异，都会整批失败；不会删掉变量或输出空白相关格。

## 运行

Python 3.9+ 依赖 `numpy` 和 `matplotlib`：

```bash
python3 python/plot.py \
  --input data/simulated_fixed_seed_relationships.csv \
  --variables metric_alpha,metric_beta,metric_gamma,metric_delta,metric_epsilon \
  --group-column group \
  --correlation-method spearman \
  --missing-policy pairwise \
  --output-prefix /path/to/output/relationship_python \
  --title "Simulated relationship matrix" \
  --dpi 320
```

输出 PNG 与 SVG。

R 4.2+ 只使用 base R：

```bash
Rscript r/plot.R \
  --input=data/simulated_fixed_seed_relationships.csv \
  --variables=metric_alpha,metric_beta,metric_gamma,metric_delta,metric_epsilon \
  --group-column=group \
  --correlation-method=spearman \
  --missing-policy=pairwise \
  --output-prefix=/path/to/output/relationship_r \
  --title="Simulated relationship matrix" \
  --dpi=320
```

输出 PNG 与 PDF。无需分组时省略 `--group-column`。

## 自适应布局与边界

矩阵允许 2–8 个连续变量，画布和字体随 `p × p` 动态调整；超过 8 个会友好报错并建议先依据研究问题预选变量，而不是生成不可读大图。分组颜色和图例随实际水平生成，变量标签长度参与画布尺寸计算。每个组在当前缺失策略下至少需要 2 个可用对象，才能支持分组分布显示。

相关矩阵用于探索和描述，不是独立证据门禁。变量筛选、离群点规则、变换、重复测量结构和抽样设计都应在上游声明；时间顺序、组别分离或相关模式均不能单独建立因果关系。
