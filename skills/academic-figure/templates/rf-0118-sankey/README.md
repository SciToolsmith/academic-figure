# 多阶段加权流向图

验证预览：[Python](../../assets/open-templates/rf-0118/preview-python.png) · [R](../../assets/open-templates/rf-0118/preview-r.png)

这是 `rf-0118` 的去案例化开放模板。它用同一观察单位在多个阶段的类别路径绘制 Sankey/alluvial 图，带宽表示记录数或正权重之和。

## 适用边界

- 适合：同一对象的多阶段状态、来源—去向、类别转移或聚合后的路径权重。
- 不适合：各阶段来自不同对象且没有一一路径键的边际汇总；此时流带会虚构转移。
- 流向只表达关联或路径，不自动表达因果、风险或显著性。

## 输入契约

CSV 一行表示一条完整路径，可以是单条观察，也可以是已聚合路径。

| 角色 | 要求 |
|---|---|
| 阶段列 | 至少 2 列；通过 `--stages` 指定，或自动识别 `stage_` 开头的列 |
| 权重列 | 可选；必须是有限正数；未指定时每行权重为 1 |
| 元数据 | `source_type`, `source_seed`, ID 等可保留，但不参与绘图 |

阶段缺失会终止绘图，不自动补成“Unknown”。如果“Unknown”是有意义的观测类别，请在源数据中明确写出。

`data/demo_flows.csv` 为固定种子生成的中性模拟演示，不代表真实科学结论。

## Python

依赖：Python 3.9+、`numpy`、`matplotlib`。

```bash
python python/plot.py \
  --input data/demo_flows.csv \
  --output-dir output \
  --stages stage_1,stage_2,stage_3,stage_4 \
  --weight weight \
  --title "Multi-stage flow overview"
```

输出：`sankey_python.png` 和 `sankey_python.svg`。

## R

依赖：R 4.2+；PNG 优先使用可选的 `ragg`，无 `ragg` 时使用系统 PNG 设备。

```bash
Rscript r/plot.R \
  --input=data/demo_flows.csv \
  --output-dir=output \
  --stages=stage_1,stage_2,stage_3,stage_4 \
  --weight=weight \
  --title="Multi-stage flow overview"
```

输出：`sankey_r.png` 和 `sankey_r.svg`。

## 自适应策略

- 画布宽度随阶段数增加，高度随单个阶段最大节点数增加。
- 节点默认按总权重降序排列；可用 `--order-mode=observed` 保留首次出现顺序，或用 `alphabetical`。
- 不默默折叠稀有节点。节点过多时会扩大画布并发出警告；若需合并，应在绘图前明确定义聚合规则。
