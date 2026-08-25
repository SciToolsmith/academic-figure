# 配对观测变化图开放模板

这个 Python/R 双实现模板用于展示同一观察单位在两个或更多有序条件下的原始轨迹、每个条件的分布摘要，以及相邻条件间的变化方向。它不会根据行顺序猜配对关系，也不默认执行显著性检验。

## 输入契约

CSV 一行表示一个对象在一个条件下的一次观测。

| 字段 | 必需 | 语义与校验 |
|---|---:|---|
| `id` | 是 | 观察单位标识；必须真实表示同一对象，不能为独立观测人工制造共同 ID |
| `condition` | 是 | 有序条件、时点或阶段；默认按首次出现顺序，或用 `--condition-order` 明确指定 |
| `value` | 是 | 同一量纲的数值；空值被识别为缺失，非空值必须为有限数值 |
| `group` | 否 | 对象间分组；一个 `id` 只能属于一个组，重复 ID 应先命名空间化 |

每个 `group + id + condition` 必须恰好一行。一个完整配对对象必须在全部全局条件下各有一个非缺失值；缺行和空值都会被区分并报告。

默认 `--incomplete-policy error`：只要存在不完整对象就停止，不生成图。只有在科学上已决定使用完整案例分析时，才显式传入 `--incomplete-policy drop`；脚本会删除该对象的全部行并报告不完整对象数与排除行数，保证同一组内各条件使用相同对象集合。

## 图形口径

- 灰度之外仍可凭线段斜率和 `↑/↓/=` 计数读取变化方向。
- 原始点保留实际 `value`；同一 ID 在各条件使用相同的轻微横向偏移。
- 箱体为第 25–75 百分位，中线为中位数，须线为 1.5×IQR 范围内最远的实际值。
- `--change-tolerance` 是与 `value` 同单位的描述性方向阈值，默认 `0`；它不代表显著性。
- 多于两个条件时只对相邻条件画线和计算方向计数。
- 基础模板不计算 P 值、置信区间或多重校正。

如需推断，应另行预先定义比较、配对检验或重复测量模型、缺失机制，以及构成多重校正的 comparison family，不能从图形自动推导。

## 演示数据

[`data/simulated_fixed_seed_demo.csv`](data/simulated_fixed_seed_demo.csv) 使用固定随机种子 `173` 生成。文件内逐行标注 `source_type=simulated` 与 `source_seed=173`；它仅演示契约和布局，不代表真实结论。

## Python

依赖：Python 3.9+、NumPy 1.22+、Matplotlib 3.5+。

```bash
python3 python/plot.py \
  --input data/simulated_fixed_seed_demo.csv \
  --output-prefix output/paired_python \
  --condition-order "Condition 1,Condition 2,Condition 3" \
  --change-tolerance 0.10 \
  --title "Simulated paired change" \
  --y-label "Simulated value"
```

输出 `output/paired_python.png`（320 DPI）与 `output/paired_python.svg`。

## R

依赖：R 4.2+；只使用 base R。

```bash
Rscript r/plot.R \
  --input data/simulated_fixed_seed_demo.csv \
  --output-prefix output/paired_r \
  --condition-order "Condition 1,Condition 2,Condition 3" \
  --change-tolerance 0.10 \
  --title "Simulated paired change" \
  --y-label "Simulated value"
```

输出 `output/paired_r.png`（320 DPI）与 `output/paired_r.svg`。两端都会记录完整/不完整对象、排除行、每条件四分位数及每个相邻转换的方向计数。

验证预览：[Python](../../assets/open-templates/rf-0173/preview-python.png) · [R](../../assets/open-templates/rf-0173/preview-r.png)

## 自适应与边界

- 组数决定 1–3 列分面；条件数和标签长度共同决定画布宽度，长条件名自动换行。
- 全部组共享 y 轴范围，便于同量纲比较；条件和组按输入首次出现顺序保持稳定。
- 多组、很多条件或大量对象仍可能造成轨迹拥挤，应根据科学问题拆分输出，而不是静默抽样。
- 适合真正配对的连续或近连续观测；不适合独立横断面样本、对象身份不可追踪的数据、层级依赖未处理的数据、生存/删失或组成数据。
