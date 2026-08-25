# Supplied regression diagnostics 通用模板

这是 `rf-0100` 的去案例化 Python/R 双实现。输入必须已经包含 `x`、`y`、`fitted` 和 `residual`；模板只绘制这些值，不拟合或选择模型，不计算系数、P 值、置信区间、R²、正态性检验或其他统计结论。

预览：[Python 成图](../../assets/open-templates/rf-0100/preview-python.png) · [R 成图](../../assets/open-templates/rf-0100/preview-r.png)

## 数据契约

UTF-8 CSV 一行一个 sample：

| 字段 | 要求 |
|---|---|
| `sample_id` | 必需、非空、全表唯一 |
| `x`, `y`, `fitted`, `residual` | 必需且每行均为有限数值；不接受空值、`NA`、`Inf` 或 `NaN` |
| 可选 group | 通过 `--group-column` 显式指定；若指定，每行非空，最多 12 个水平，每组至少 2 个对象 |

`x`、`y` 和 `fitted` 在整表中必须各有变异。`residual` 被视为来源提供的诊断量：脚本不会以 `y - fitted` 重算、覆盖或判定它是哪种残差，因此原始残差、标准化残差、deviance residual 等语义必须由上游说明。

演示数据由固定伪随机种子 `100` 生成，包含 72 个中性对象和 3 个无领域含义的组别；每行以 `data_status=SIMULATED`、`simulation_seed=100` 标记。

## 三联结构

1. Relationship：`x` 对 `y` 的实心点，以及同一 `x` 上的 supplied fitted 空心菱形。脚本不把 fitted 点连接成新拟合曲线。
2. Marginal distributions：`x` 和 `y` 的独立边缘直方图；有 group 时叠加组别密度轮廓。
3. Residual diagnostic：supplied residual 对 supplied fitted 的散点和零参考线；不添加平滑趋势或检验。

图标题、面板标签和运行日志均明确标注 supplied diagnostics，避免把绘图误报成模型拟合或统计验证。

## 运行

Python 3.9+ 依赖 `numpy` 和 `matplotlib`：

```bash
python3 python/plot.py \
  --input data/simulated_fixed_seed_supplied_diagnostics.csv \
  --group-column group \
  --output-prefix /path/to/output/regression_diagnostics_python \
  --title "Simulated supplied regression diagnostics" \
  --dpi 320
```

输出 PNG 与 SVG。

R 4.2+ 只使用 base R：

```bash
Rscript r/plot.R \
  --input=data/simulated_fixed_seed_supplied_diagnostics.csv \
  --group-column=group \
  --output-prefix=/path/to/output/regression_diagnostics_r \
  --title="Simulated supplied regression diagnostics" \
  --dpi=320
```

输出 PNG 与 PDF。无需分组时省略 `--group-column`。

## 布局与解释边界

模板允许 5–5000 个对象；点大小随样本数调整，组颜色、形状和图例随实际水平生成。超过边界会友好报错，不抽样或删行。

残差形状、边缘分布、组别分离或 fitted 与观测接近程度只描述输入。模板不能证明模型适合、假设成立、效应显著或关系具有因果性；模型公式、训练过程、残差定义、重复测量结构和推断依据必须由来源分析提供。
