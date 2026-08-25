# rf-0172 通用森林图模板

该模板把已经计算好的点估计和置信区间绘制为森林图。它不会拟合模型、重算置信区间、调整 P 值或根据 P 值筛选记录。Python 与 R 读取同一份长表 CSV，按输入顺序生成动态行数和动态面板。

验证预览：[Python](../../assets/open-templates/rf-0172/preview-python.png) · [R](../../assets/open-templates/rf-0172/preview-r.png)

`demo/demo_simulated_seed172.csv` 是明确标记的模拟演示数据，使用固定随机种子 `172`。其中的名称、估计值和 P 值不代表真实研究结论。

## 依赖

- Python 3.9+ 与 Matplotlib。
- R 4.x；只使用 base R 和 `grDevices`，无需额外包。

安装 Python 依赖：

```bash
python3 -m pip install matplotlib
```

## CSV 字段契约

| 字段 | 必需 | 语义与约束 |
|---|---:|---|
| `label` | 是 | 行标签；不能为空。 |
| `estimate` | 是 | 点估计；必须是有限数值。 |
| `ci_low` | 是 | 置信区间下界；必须满足 `ci_low < ci_high`。 |
| `ci_high` | 是 | 置信区间上界；点估计必须位于闭区间 `[ci_low, ci_high]` 内。 |
| `panel` | 否 | 面板名称；缺失时使用 `Forest plot`。面板按首次出现顺序排列。 |
| `section` | 否 | 面板内分节标题；同一节的标签按首次出现顺序排列。 |
| `series` | 否 | 同一标签下的模型、时间点或组别；缺失时使用 `Estimate`。多系列自动错位并生成图例。 |
| `metric` | 否 | 效应类型；缺失时按加性效应处理。允许值见下文。 |
| `null_value` | 否 | 无效值参考线。加性效应默认 `0`；比值效应必须为 `1`。 |
| `p_value` | 否 | 来源提供的 P 值，范围必须为 `[0, 1]`；仅作为文字显示，不据此改变点样式。 |
| `n` | 否 | 来源提供的样本量或事件数；必须为正整数，仅作为文字显示。 |

演示 CSV 还包含 `data_status=SIMULATED` 和 `simulation_seed=172`。真实数据可以省略这两列；如果声明 `SIMULATED`，则必须同时提供一个全表一致的 `simulation_seed`。

`panel + section + label + series` 必须唯一。脚本遇到无效记录会停止并报告行号，不会静默删除记录，也不会在真实输入失败后改用演示数据。

## 加性效应与比值效应边界

一个面板只能包含一种效应族，并且所有行必须使用同一条无效值参考线。

加性效应使用线性轴。可用的 `metric` 值为：

```text
additive, difference, mean_difference, risk_difference,
beta, coefficient, correlation, log_ratio, log_odds, log_hazard
```

- 默认 `null_value=0`。
- 估计值和区间可以跨越零。
- `log_ratio`、`log_odds` 和 `log_hazard` 表示已经取对数的效应，因此属于加性效应：使用线性轴和零参考线。
- 可以显式提供非零的加性参考值，但该参考值必须有研究设计依据，脚本不会替用户解释其含义。

比值效应使用对数轴。可用的 `metric` 值为：

```text
ratio, odds_ratio, risk_ratio, rate_ratio,
hazard_ratio, prevalence_ratio
```

- `null_value` 必须精确为 `1`。
- `estimate`、`ci_low` 和 `ci_high` 都必须严格大于零。
- 原始比值不能放在线性轴上；已经取对数的比值则应使用上面的加性效应类型。
- 一个面板内不能混用原始比值和加性/对数效应；需要拆成不同 `panel`。

## 运行演示

在模板根目录运行：

```bash
python3 python/plot.py
Rscript r/plot.R
```

默认产物：

```text
output/forest_python.png
output/forest_python.svg
output/forest_r.png
output/forest_r.pdf
```

## 使用真实数据

Python：

```bash
python3 python/plot.py \
  --input path/to/estimates.csv \
  --output-prefix output/my_forest_python \
  --title "Forest plot of supplied estimates" \
  --dpi 320
```

R：

```bash
Rscript r/plot.R \
  --input path/to/estimates.csv \
  --output-prefix output/my_forest_r \
  --title "Forest plot of supplied estimates" \
  --dpi 320
```

相对路径按运行命令所在目录解析；脚本自身的默认数据和输出位置则根据脚本位置推导，不包含机器相关的绝对路径。

## 校验范围

两种实现都会在绘图前检查：

- 必需列、空标签、非数值、缺失值和无穷值；
- `ci_low < ci_high` 且点估计位于区间内；
- 重复的 `panel/section/label/series`；
- 每个面板的效应族和参考线一致性；
- 比值效应的正值条件、`null_value=1` 和对数轴条件；
- `p_value` 的 `[0, 1]` 范围及 `n` 的正整数条件；
- 演示状态和固定种子标记的一致性。

这些检查只能验证绘图输入的一致性，不能证明上游模型、效应方向、置信区间覆盖率、P 值口径或多重检验方法正确。
