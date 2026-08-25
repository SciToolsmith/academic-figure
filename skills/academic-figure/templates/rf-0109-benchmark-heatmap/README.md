# rf-0109 通用 benchmark heatmap 模板

该模板把 `method + metric + value` 长表绘制为性能矩阵。单元格文字保留原始值；颜色只使用指标说明文件中预先声明的尺度做方向对齐和 `0–1` 标准化，不直接比较量纲不同的原值，也不做显著性检验。

演示文件明确标记为中性模拟数据，固定随机种子为 `109`：

- `demo/demo_benchmark_seed109.csv`：9 个方法 × 7 个指标，共 63 个显式方法/指标组合，其中 2 个 `value` 为显式 NA。
- `demo/demo_metric_spec.csv`：独立指标定义，不从观测到的最好/最差值反推尺度。

预览：[Python 成图](../../assets/open-templates/rf-0109/preview-python.png) · [R 成图](../../assets/open-templates/rf-0109/preview-r.png)

## 依赖

- Python 3.9+、Matplotlib 和 NumPy。
- R 4.x，仅使用 base R、`graphics` 和 `grDevices`。

```bash
python3 -m pip install matplotlib numpy
```

## Benchmark 长表契约

| 字段 | 必需 | 约束 |
|---|---:|---|
| `method` | 是 | 方法名称，不能为空。 |
| `metric` | 是 | 必须存在于 metric spec。 |
| `value` | 是 | 有限数值；空字符串表示显式 NA。不能使用 `NA`、`Inf` 等字符串代替空值。 |

每个 `method + metric` 只能出现一次。表格必须显式包含所有方法与所有指标的笛卡尔组合；缺失值保留该行并将 `value` 留空，不能直接省略整行。

演示表还包含 `data_status=SIMULATED` 和 `simulation_seed=109`。真实输入可以省略；声明模拟数据时，每行必须使用同一个正整数种子。

## 独立 metric spec

| 字段 | 语义与约束 |
|---|---|
| `metric` | 与 benchmark 长表对应的唯一 ID。 |
| `label` | 图中显示名称。 |
| `direction` | `higher` 或 `lower`，明确较高还是较低更好。 |
| `display` | `decimal`、`percent`、`integer` 或 `scientific`。只控制原值文字格式。 |
| `digits` | 显示小数位，整数 `0–6`。 |
| `scale_min` | 由领域或评测协议预先声明的可比较下界。 |
| `scale_max` | 预先声明的上界，必须大于 `scale_min`。 |

非缺失值必须落在声明区间内；脚本不会裁剪越界值。颜色性能分数计算为：

```text
higher is better: (value - scale_min) / (scale_max - scale_min)
lower is better:  1 - (value - scale_min) / (scale_max - scale_min)
```

因此颜色始终表示方向一致的 `0=较差、1=较好` 标准化性能，而单元格文字仍显示原始量纲。只有在 `scale_min/scale_max` 对各指标具有科学或协议依据时，这些颜色才可横向比较。不得用当前样本的观测极值冒充预设尺度。

## 排名、NA 和并列规则

- 只有全部指标均非 NA 的方法进入总体排名。
- 总体分数是各指标标准化性能的等权算术均值。
- 总体分数在绝对容差 `1e-12` 内相等时采用 competition rank，例如 `1, 1, 3`；并列内部按方法名称排序以保证稳定输出。
- 含任意 NA 的方法标记为 `NR`，置于完整方法之后；先按非缺失指标数、再按可用指标的描述性均值、最后按名称排序。可用指标均值不作为正式排名。
- NA 单元格显示灰色和 `NA`，不填补、不赋零，也不参与颜色或总体排名。

该排名只描述用户声明尺度下的等权汇总，不代表统计显著性、实际等效性或领域优越性。

## 运行

Python：

```bash
python3 python/plot.py \
  --input demo/demo_benchmark_seed109.csv \
  --metric-spec demo/demo_metric_spec.csv \
  --output-prefix output/benchmark_python \
  --dpi 320
```

R：

```bash
Rscript r/plot.R \
  --input demo/demo_benchmark_seed109.csv \
  --metric-spec demo/demo_metric_spec.csv \
  --output-prefix output/benchmark_r \
  --dpi 320
```

Python 生成 PNG + SVG；R 生成 PNG + 单页 PDF。默认输入路径根据脚本位置推导，默认输出前缀位于运行命令的当前目录，不包含机器相关绝对路径。

## 动态布局与边界

画布、行标签和单元格字号随方法数、指标数及名称长度调整。为避免生成不可读的超宽表格，单图最多接受 18 个指标；超过时脚本明确停止并要求按有意义的指标族拆分。方法上限为 80，超过时应筛选或拆分，而不是继续缩小字体。

校验只能确认矩阵完整性、方向、格式、尺度、排名和 NA 处理自洽，不能证明指标定义、范围、等权汇总或方法间比较在特定研究问题中合理。
