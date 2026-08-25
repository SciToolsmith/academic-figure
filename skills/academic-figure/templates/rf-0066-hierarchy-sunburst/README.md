# 层级旭日图开放模板

该模板把一棵带叶节点权重的树绘制为旭日图。它适合展示分类体系与组成规模，不表示样本间距离、因果顺序或统计显著性。

## 数据契约

输入为 CSV，每行一个节点：

| 字段 | 必需 | 语义与校验 |
|---|---:|---|
| `node_id` | 是 | 全表唯一、非空的节点标识 |
| `parent_id` | 是 | 根节点留空；其余节点必须引用现有节点 |
| `label` | 是 | 展示名称 |
| `value` | 叶节点是 | 有限正数；内部节点必须留空，汇总值由脚本自下而上计算 |
| `color_group` | 否 | 颜色分组；缺失时继承一级分支 |
| `order` | 否 | 同级节点排序，缺失时按输入顺序 |

脚本要求恰好一个根节点，拒绝重复 ID、多个父节点、环、孤立节点、内部节点手填权重和非正叶节点权重。扇区面积来自叶节点权重汇总，不会把父子值重复相加。

## 演示数据与预览

[`data/simulated_fixed_seed_demo.csv`](data/simulated_fixed_seed_demo.csv) 是固定种子 `66` 的中性演示层级，不代表真实分类或科学结论。

- [Python 成图](../../assets/open-templates/rf-0066/preview-python.png)
- [R 成图](../../assets/open-templates/rf-0066/preview-r.png)

## Python

依赖 Python 3.9+ 和 Matplotlib：

```bash
python3 python/plot.py \
  --input data/simulated_fixed_seed_demo.csv \
  --output-prefix output/sunburst_python \
  --title "Simulated hierarchical composition"
```

输出 320 DPI PNG 和 SVG。

## R

仅依赖 R 4.2+ base R：

```bash
Rscript r/plot.R \
  --input=data/simulated_fixed_seed_demo.csv \
  --output-prefix=output/sunburst_r \
  --title="Simulated hierarchical composition"
```

输出 320 DPI PNG 和单页 PDF。

## 自适应与边界

- 最多 5 个可见层级、120 个节点；过深或过密时应改用树图、冰柱图或分层表格。
- 小扇区默认不放文字，避免以缩小字号掩盖信息拥挤；完整名称仍保留在源表。
- 颜色只区分分支，不代表连续数值或优劣顺序。
- 若权重属于不同分母、可重叠集合或网络节点，不应套用本模板。
