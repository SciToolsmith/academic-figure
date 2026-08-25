# 嵌入图与样本组成开放模板

该模板把上游已计算的二维嵌入与同一批观察记录的样本组成并列展示。左图回答“观察落在什么位置”，右图回答“各样本由哪些类别构成”；绘图脚本不计算 UMAP/t-SNE，也不做聚类或差异检验。

## 数据契约

输入 CSV 每行一条观察：

| 字段 | 必需 | 语义与校验 |
|---|---:|---|
| `observation_id` | 是 | 全表唯一观察标识 |
| `sample_id` | 是 | 样本标识，右侧分母按此字段建立 |
| `x`, `y` | 是 | 上游生成的有限二维坐标 |
| `category` | 是 | 上游确定的类别，颜色与组成使用同一编码 |
| `sample_order` | 否 | 样本显示顺序；同一样本必须一致 |

右侧计数和比例直接由左侧同一批行汇总。脚本报告总行数、每个样本的分母和缺失排除；不会把另一个表中的百分比拼接到嵌入图旁边。

## 演示数据与预览

[`data/simulated_fixed_seed_demo.csv`](data/simulated_fixed_seed_demo.csv) 由 [`data/generate_demo.py`](data/generate_demo.py) 使用固定种子 `41` 生成，所有行标记 `source_type=simulated`。坐标、类别与样本构成均为中性演示，不代表真实生物结构。

- [Python 成图](../../assets/open-templates/rf-0041/preview-python.png)
- [R 成图](../../assets/open-templates/rf-0041/preview-r.png)

## Python

依赖 Python 3.9+ 和 Matplotlib：

```bash
python3 python/plot.py \
  --input data/simulated_fixed_seed_demo.csv \
  --output-prefix output/embedding_python \
  --title "Simulated embedding and sample composition"
```

输出 320 DPI PNG 和 SVG。

## R

仅依赖 R 4.2+ base R：

```bash
Rscript r/plot.R \
  --input=data/simulated_fixed_seed_demo.csv \
  --output-prefix=output/embedding_r \
  --title="Simulated embedding and sample composition"
```

输出 320 DPI PNG 和单页 PDF。

## 自适应与边界

- 支持 2–40 个样本、2–16 个类别和最多 200,000 条观察。
- 点的透明度会按数据量调整；组成面板始终显示实际计数分母。
- 类别是离散编码，不应用连续色带；类别过多时应先确认科学上可解释的合并方案。
- 不同样本的捕获量、抽样深度或缺失机制不一致时，组成比例不能直接解释为总体丰度。
