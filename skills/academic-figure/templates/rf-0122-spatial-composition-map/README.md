# 空间分布与组成符号开放模板

该模板在用户提供的边界和投影坐标上绘制组成饼符号：位置表达空间分布，符号面积表达总量，扇区表达组成。它不下载底图、不猜测坐标系，也不把经纬度直接当作等距平面。

## 数据契约

`composition.csv` 每行一个地点—组分：

| 字段 | 必需 | 语义与校验 |
|---|---:|---|
| `location_id` | 是 | 地点标识 |
| `label` | 是 | 展示名称；同一地点必须一致 |
| `x`, `y` | 是 | 同一已知投影坐标系中的有限坐标 |
| `component` | 是 | 组分类别，最多 8 类 |
| `value` | 是 | 有限非负数；地点总和必须大于 0 |
| `location_order` | 否 | 地点绘制顺序；同一地点必须一致 |

`boundaries.csv` 每行一个边界顶点：`polygon_id`, `vertex_order`, `x`, `y`。每个多边形至少三个顶点，脚本按顺序闭合。两份文件的坐标必须使用同一投影和单位，并通过 `--crs-label` 记录。

## 演示数据与预览

[`data/simulated_fixed_seed_composition.csv`](data/simulated_fixed_seed_composition.csv) 与 [`data/simulated_fixed_seed_boundaries.csv`](data/simulated_fixed_seed_boundaries.csv) 是固定种子 `122` 的抽象空间演示，不对应任何真实地区或调查结论。

- [Python 成图](../../assets/open-templates/rf-0122/preview-python.png)
- [R 成图](../../assets/open-templates/rf-0122/preview-r.png)

## Python

依赖 Python 3.9+ 和 Matplotlib：

```bash
python3 python/plot.py \
  --composition data/simulated_fixed_seed_composition.csv \
  --boundaries data/simulated_fixed_seed_boundaries.csv \
  --output-prefix output/spatial_python \
  --crs-label "Simulated projected units"
```

输出 320 DPI PNG 和 SVG。

## R

仅依赖 R 4.2+ base R：

```bash
Rscript r/plot.R \
  --composition=data/simulated_fixed_seed_composition.csv \
  --boundaries=data/simulated_fixed_seed_boundaries.csv \
  --output-prefix=output/spatial_r \
  --crs-label="Simulated projected units"
```

输出 320 DPI PNG 和单页 PDF。

## 自适应与边界

- 支持 1–80 个地点和最多 8 个组分；地点过密时应改用分面、规则网格或交互地图。
- 符号面积与地点总量成比例，半径不与总量成比例；图注会报告此规则。
- 坐标、边界和 CRS 来自用户，不在脚本中联网补齐或静默重投影。
- 组分分母、采样努力或空间覆盖不一致时，必须先解决可比性，不能靠符号大小掩盖。
