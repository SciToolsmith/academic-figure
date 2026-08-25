# 聚类节点—边网络开放模板

该模板展示已经确定的节点、边、坐标和分组。它负责审查并表达网络结构，不在绘图阶段重新做社区发现、布局优化、相关性计算或显著性筛选。

## 数据契约

`nodes.csv`：

| 字段 | 必需 | 语义与校验 |
|---|---:|---|
| `node_id` | 是 | 全表唯一节点标识 |
| `label` | 是 | 展示名称 |
| `x`, `y` | 是 | 上游确定的有限二维坐标 |
| `cluster` | 是 | 上游确定的分组，不由脚本推断 |
| `size` | 否 | 有限正数，只控制节点面积，默认 1 |
| `show_label` | 否 | `true/false`；明确控制是否标注，默认 false |

`edges.csv`：

| 字段 | 必需 | 语义与校验 |
|---|---:|---|
| `source`, `target` | 是 | 必须引用 `nodes.csv` 中不同节点 |
| `weight` | 否 | 有限正数，只控制线宽，默认 1 |
| `edge_group` | 否 | 可选边类型；只用于线型，不解释为方向或显著性 |

重复的无向边会被拒绝，避免不透明的叠加加权。若研究对象是有向网络，应先明确方向语义，再扩展箭头编码。

## 演示数据与预览

[`data/simulated_fixed_seed_nodes.csv`](data/simulated_fixed_seed_nodes.csv) 与 [`data/simulated_fixed_seed_edges.csv`](data/simulated_fixed_seed_edges.csv) 是固定种子 `44` 的中性模拟网络，仅演示结构。

- [Python 成图](../../assets/open-templates/rf-0044/preview-python.png)
- [R 成图](../../assets/open-templates/rf-0044/preview-r.png)

## Python

依赖 Python 3.9+ 和 Matplotlib：

```bash
python3 python/plot.py \
  --nodes data/simulated_fixed_seed_nodes.csv \
  --edges data/simulated_fixed_seed_edges.csv \
  --output-prefix output/network_python \
  --title "Simulated supplied network structure"
```

输出 320 DPI PNG 和 SVG。

## R

仅依赖 R 4.2+ base R：

```bash
Rscript r/plot.R \
  --nodes=data/simulated_fixed_seed_nodes.csv \
  --edges=data/simulated_fixed_seed_edges.csv \
  --output-prefix=output/network_r \
  --title="Simulated supplied network structure"
```

输出 320 DPI PNG 和单页 PDF。

## 自适应与边界

- 建议 5–120 个节点、最多 500 条边和不超过 12 个分组。
- 坐标范围会等比例缩放；Python/R 都不会重新布局，因此结果可复核。
- 标签仅按 `show_label` 显示，不因节点大小或名称自动挑选。
- 边的存在、权重、分组和节点聚类必须来自可审查的上游过程；本模板不替代网络推断。
