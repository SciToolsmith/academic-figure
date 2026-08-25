# 分面组成堆积图开放模板

这个 Python/R 双实现模板将长表中的多个样本组成画成分面堆积柱。输入必须明确声明是已经归一化的比例还是原始非负值；脚本绝不根据数值范围猜测，也不会静默归一化。

预览：[Python 成图](../../assets/open-templates/rf-0001/preview-python.png) · [R 成图](../../assets/open-templates/rf-0001/preview-r.png)

## 输入契约

CSV 一行表示一个样本中的一个组分：

| 字段 | 约束 |
|---|---|
| `facet` | 非空面板标识；按首次出现顺序布局 |
| `sample` | 非空样本标识；与 `facet` 共同定义一根柱 |
| `component` | 非空组分；全局首次出现顺序为默认堆积顺序 |
| `value` | 有限、非负数值，不允许缺失 |

每个 `(facet, sample, component)` 必须唯一。每根柱必须显式包含全局全部组分，包括数值为 0 的组分；脚本不会把缺行当成 0。每个样本的总和必须大于 0。

## 输入尺度与归一化

运行时必须同时指定：

- `--input-mode proportion --normalize false`：数据已是比例。每个样本必须在 `1 ± --sum-tolerance` 内求和为 1；超出即停止，不修改数据。
- `--input-mode value --normalize true`：输入是原始非负值，显式除以各样本总和后绘制比例；原始总和仍会记录。
- `--input-mode value --normalize false`：绘制原始堆积值，柱高保留样本总量差异。

`proportion + normalize=true` 会报错，因为它混淆了“验证已有比例”和“重新归一化”。默认和容差为 `1e-6`，可用 `--sum-tolerance` 明确修改。

## 顺序与颜色

- `--sample-order input` 保留各分面首次出现顺序；也可选 `alphabetical` 或按原始总和降序的 `total-desc`。
- 可选 [`data/component_style.csv`](data/component_style.csv) 明确 `component,label,color,order`；颜色必须为唯一的 `#RRGGBB`，order 必须唯一。
- 不提供 style 时，脚本按首次出现顺序自动扩展定性色板；图例与白色边界共同区分组分。

## 演示数据

[`data/simulated_fixed_seed_demo.csv`](data/simulated_fixed_seed_demo.csv) 使用固定种子 `1` 生成 3 个中性分面、24 个样本和 8 个组分，并逐行标注 `source_type=simulated`、`source_seed=1`。它只演示契约，不代表真实组成差异。

## Python

依赖：Python 3.9+、NumPy 1.22+、Matplotlib 3.5+。

```bash
python3 python/plot.py \
  --input data/simulated_fixed_seed_demo.csv \
  --style data/component_style.csv \
  --output-prefix output/composition_python \
  --input-mode proportion \
  --normalize false \
  --sample-order input \
  --title "Simulated faceted composition"
```

输出 `output/composition_python.png`（320 DPI）与 `output/composition_python.svg`。

## R

依赖：R 4.2+；只使用 base R。

```bash
Rscript r/plot.R \
  --input data/simulated_fixed_seed_demo.csv \
  --style data/component_style.csv \
  --output-prefix output/composition_r \
  --input-mode proportion \
  --normalize false \
  --sample-order input \
  --title "Simulated faceted composition"
```

输出 `output/composition_r.png`（320 DPI）与 `output/composition_r.svg`。两端都会记录输入行、分面、样本、组分、原始总和范围、最大组成和偏差及标签步长。

## 可读性边界

- 最多 20 个组分和每分面 60 个样本；超限会明确停止。超过约 12 个组分时，颜色判读本身已变困难，应考虑聚合规则、小倍图或其他组成表达。
- 样本多于 20 个时仍绘制全部柱，只按明确报告的步长减少 x 轴文字，不抽样数据。
- 分面、样本数和标签长度共同决定画布；全部分面共享 y 轴。
- 堆积图适合读取整体构成，不适合精确比较远离共同基线的中间组分，也不解决组成数据的统计建模问题。
