# 分组雨云图开放模板

这是一个去案例化的 Python/R 双实现模板：用同一数值尺度比较若干组的分布形状、中位数、四分位范围和原始观测。一个 CSV 同时驱动两端，不做地点映射、单位缩放、坐标反转或结论性标注。

## 图形契约

- 问题：不同独立组的一维数值分布有何异同？
- 观察单位：CSV 的一行是一条原始观测。
- 证据：精确 x 坐标的原始点、箱线摘要，以及条件允许时的平滑分布轮廓。
- 设计：默认把行视为独立观测；`id` 只用于重复单位检查和稳定排点，不连接个体，也不改变统计量。

## 输入字段

| 字段 | 必需 | 语义与校验 |
|---|---:|---|
| `group` | 是 | 非空类别；按输入中首次出现的顺序显示 |
| `value` | 是 | 同一量纲下的有限数值；脚本不做隐式变换、标准化或反向 |
| `facet` | 否 | 非空面板类别；存在时所有面板共享同一 x 轴范围 |
| `id` | 否 | 非空观察单位标识；在同一 `facet + group` 内必须唯一 |

其他列会原样留在输入中但不参与绘图。缺失、非数值、无穷值或违反唯一性都会在绘图前终止；脚本不静默删行，也不自动去重。

箱体为第 25–75 百分位，中线为中位数，须线延伸到 1.5×IQR 范围内最远的实际观测。原始点只做确定性的纵向错开，x 坐标不抖动。KDE 使用高斯核和 `sd × n^(-1/5)` 带宽；少于 3 个观测、少于 3 个不同值或近零方差时不画 KDE，但仍保留箱线和原始点。每组 KDE 高度独立归一化，因此不能跨组比较峰高。

## 演示数据

[`data/simulated_fixed_seed_demo.csv`](data/simulated_fixed_seed_demo.csv) 是随机种子 `104` 生成的中性模拟数据。CSV 内的 `source_type=simulated` 和 `source_seed=104` 也明确标注来源；它只用于演示字段与布局，不代表真实研究结果。

## Python

依赖：Python 3.9+、`numpy`、`matplotlib`。

```bash
python3 python/plot.py \
  --input data/simulated_fixed_seed_demo.csv \
  --output-prefix output/raincloud_python \
  --title "Simulated group distributions" \
  --x-label "Simulated value"
```

输出：`output/raincloud_python.png`（300 DPI）与 `output/raincloud_python.svg`。

## R

依赖：R 4.2+；只使用 base R。PNG 优先使用 R 的 Cairo 能力，SVG 使用系统图形设备。

```bash
Rscript r/plot.R \
  --input data/simulated_fixed_seed_demo.csv \
  --output-prefix output/raincloud_r \
  --title "Simulated group distributions" \
  --x-label "Simulated value"
```

输出：`output/raincloud_r.png`（300 DPI）与 `output/raincloud_r.svg`。

两端都会在标准输出中记录总行数、分面数、组数、各组 `n/min/median/max`、KDE 是否绘制及带宽，并明确报告排除行数为 0。

验证预览：[Python](../../assets/open-templates/rf-0104/preview-python.png) · [R](../../assets/open-templates/rf-0104/preview-r.png)

## 验证记录

上述演示命令已分别从空白进程运行：Python 3.9.6 + NumPy 2.0.2 + Matplotlib 3.9.4，以及 R 4.5.3（base R，Cairo 可用）。两端均读取 240 行、排除 0 行，识别 2 个分面和 4 个组，并各自成功导出 PNG 与可解析的 SVG。

## 自适应行为

- 分面数量决定 1–3 列布局；画布高度随单面板最大组数增加。
- 组标签长度会增加面板宽度或左边距；组标签直接附带样本量，颜色不是唯一编码。
- 全部分面共享数值范围，组颜色按全局首次出现顺序保持一致。
- 单组超过 2,000 个点时，Python 的 SVG 会将该点层栅格化以控制文件大小；数据不抽样。R 不抽样，但超大点云的 SVG 可能很大。

## 适用与不适用

适合独立组的连续或近连续原始观测，以及需要同时看到分布、稳健位置摘要和样本量的描述性比较。

以下情况不应直接套用：

- 配对或重复测量，且个体内变化是主要证据；应使用配对点线、变化量或层级模型结果。
- 聚类、家系、批次或空间依赖需要进入不确定性估计；本模板不计算置信区间或显著性。
- 生存/删失、组成数据、离散小计数，或概率边界需要专门统计处理。
- 组或分面非常多；即使画布会扩展，通常仍应事先定义科学上合理的拆分或聚合规则。

KDE、箱线和原始点都是描述性表达，不自动支持因果、显著性或总体推断。投稿前仍需按最终版面检查字体、色觉可辨性、单位、变换和领域解释。
