# rf-0164 通用有序响应曲线模板

该模板把数值型有序 `x` 上的原始重复观测或预汇总响应绘制为点线曲线。Python 与 R 读取同一份长表 CSV；脚本不会平滑、插值未采样位置、搜索最优峰值或进行显著性检验。

`demo/demo_simulated_seed164.csv` 是中性模拟演示数据，明确标记为 `SIMULATED`，固定随机种子为 `164`。其中的曲线和区间不代表真实研究结果。

## 依赖

- Python 3.9+ 与 Matplotlib。
- R 4.x；仅使用 base R、`graphics` 和 `grDevices`。

安装 Python 依赖：

```bash
python3 -m pip install matplotlib
```

## CSV 字段契约

每条曲线由 `panel + group + series` 确定。

| 字段 | 必需 | 语义与约束 |
|---|---:|---|
| `series` | 是 | 曲线系列，例如测量通道或方案；不能为空。 |
| `group` | 是 | 比较组；不能为空。颜色按组分配，线型和点型按系列分配。 |
| `x` | 是 | 有序位置，必须是有限数值。脚本解析为数值后排序，绝不按字符串排序。每条曲线至少需要两个不同的 `x`。 |
| `y` | 是 | 响应值，必须是有限数值。 |
| `data_mode` | 是 | `raw` 或 `summary`；同一面板只能使用一种模式。 |
| `replicate` | 否 | 原始重复观测 ID。一个曲线在同一 `x` 有多行 `raw` 数据时必须提供且组内唯一；`summary` 行不得填写。 |
| `panel` | 否 | 面板标题；缺失时使用 `Ordered response`，按首次出现顺序布局。 |
| `y_lower` | 否 | 来源提供的汇总区间下界；仅用于 `summary`。必须与 `y_upper` 同时提供并满足 `y_lower < y_upper`。 |
| `y_upper` | 否 | 来源提供的汇总区间上界；`y` 必须位于闭区间 `[y_lower, y_upper]` 内。 |
| `x_scale` | 否 | `linear` 或 `log`；默认 `linear`，同一面板必须一致。 |

演示 CSV 还包含 `data_status=SIMULATED` 和 `simulation_seed=164`。真实数据可以省略这两列；一旦声明 `SIMULATED`，每行都必须提供同一个正整数固定种子。

真实输入读取或验证失败时脚本立即停止，不会删除无效行，也不会改用演示数据。

## 原始观测与预汇总值

`data_mode=raw`：

- 淡色点表示输入中的每条原始观测；
- 每个 `x` 的粗点线表示这些观测的算术均值；
- 不计算置信区间、标准误、检验或平滑曲线；
- `replicate` 只用于标识和验证重复观测，不自动连接成个体轨迹。

`data_mode=summary`：

- `y` 被视为来源已经计算好的汇总值，按原值绘制；
- 如果提供 `y_lower/y_upper`，按来源区间绘制误差条；
- 脚本不会重新计算、补齐或解释区间口径。

一个面板不能混合两种模式。若需要并列展示，应使用不同的 `panel`，避免让原始观测和汇总值看起来处于同一统计层级。

## `x` 的排序与坐标尺度

`x` 必须直接编码为数值，例如 `1, 2, 10`，不能使用 `T1, T2, T10`、`low, medium, high` 等字符串标签。脚本始终按数值顺序连接输入中实际存在的位置，不生成未采样的 `x`。

- `x_scale=linear`：默认选择。适用于相等的绝对差值具有可比意义的时间、位置、剂量或条件。
- `x_scale=log`：仅在倍数变化、比例间隔或跨数量级比较有科学意义时显式使用；面板内所有 `x` 必须严格大于零。

对数轴只改变显示坐标，不修改 CSV 中的 `x`，也不自动对 `y` 取对数。脚本不会根据数据跨度或曲线外观自动选择对数轴。

## 运行演示

在模板根目录运行，并自行指定输出前缀：

```bash
python3 python/plot.py \
  --output-prefix output/ordered_response_python

Rscript r/plot.R \
  --output-prefix output/ordered_response_r
```

Python 生成高分辨率 PNG 和 SVG；R 生成高分辨率 PNG 和单页 PDF。未提供 `--output-prefix` 时，输出到当前工作目录，而不是写死到模板内部路径。

验证预览：[Python](../../assets/open-templates/rf-0164/preview-python.png) · [R](../../assets/open-templates/rf-0164/preview-r.png)

## 使用真实数据

Python：

```bash
python3 python/plot.py \
  --input path/to/ordered_response.csv \
  --output-prefix output/my_response_python \
  --title "Ordered response curves" \
  --x-label "Ordered input" \
  --y-label "Response" \
  --dpi 320
```

R：

```bash
Rscript r/plot.R \
  --input path/to/ordered_response.csv \
  --output-prefix output/my_response_r \
  --title "Ordered response curves" \
  --x-label "Ordered input" \
  --y-label "Response" \
  --dpi 320
```

面板行列数、画布大小、配色、点型、线型和图例字号会随面板数、组数、系列数和标签长度调整。

## 解释边界

曲线只描述输入数据在已观测 `x` 上的变化。局部最高点可能来自采样网格、随机变异或上游汇总过程；不能仅凭图上的峰值声称存在最优条件、转折点、阈值或显著差异。此类结论需要与研究设计相符的独立统计方法。

脚本的校验只能证明绘图字段、重复观测标识、区间顺序和坐标尺度条件内部一致，不能证明上游数据质量、算术均值是否适合作为科学摘要、区间覆盖率或组间可比性。
