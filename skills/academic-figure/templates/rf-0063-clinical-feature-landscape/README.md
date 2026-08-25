# Mixed clinical feature landscape 通用模板

这是 `rf-0063` 的去案例化 Python/R 双实现。模板把一行一个 sample 的混合型特征绘制为矩阵；所有特征语义、颜色和顺序都来自显式 feature spec，不猜测数据类型，也不聚类或自动重排样本。

预览：[Python 成图](../../assets/open-templates/rf-0063/preview-python.png) · [R 成图](../../assets/open-templates/rf-0063/preview-r.png)

## 两张输入表

### Samples CSV

| 字段 | 要求 |
|---|---|
| `sample_id` | 必需、非空、全表唯一 |
| `sample_label` | 必需、非空；与 ID 一起显示 |
| `display_order` | 必需、正整数、全表唯一；这是唯一的样本排序依据 |
| feature 列 | 必须覆盖 spec 中每个 `feature_id` |

脚本按 `display_order` 排序，不使用 sample ID、取值、缺失比例或聚类结果排序。缺失值只接受空单元格或精确字符串 `NA`；字符串 `0` 是合法观测，不是缺失。

### Feature spec CSV

每行一个特征：

| 字段 | 要求 |
|---|---|
| `feature_id`, `feature_label` | 必需、非空；ID 唯一且必须是 samples 列 |
| `feature_type` | 必须是 `continuous`、`categorical`、`binary` 之一 |
| `display_order` | 正整数且唯一，控制特征列顺序 |
| `display_min`, `display_max` | continuous 必需、有限且 `min < max`；其他类型必须留空 |
| `levels` | categorical 使用 `|` 分隔的 2–8 个显式水平；binary 必须恰好两个；continuous 留空 |
| `colors` | `|` 分隔的 `#RRGGBB`；continuous 恰好两个端点色，其他类型与 levels 一一对应 |
| `missing_label`, `missing_color` | 必需；缺失颜色不得与该特征任一非缺失颜色相同 |

连续值超出显式显示域会整批失败，不裁剪或自动扩展色域。未知分类/二元水平、无效数值、重复 ID/顺序或缺少 spec 列也会失败。缺失单元使用专用底色和斜线纹理，绝不转成 0 或最低连续值。

演示数据由固定伪随机种子 `63` 生成，含 30 个中性对象、2 个 continuous、2 个 categorical、2 个 binary 特征。两表均以 `data_status=SIMULATED`、`simulation_seed=63` 标记；脚本检查表内及表间 provenance 一致。

## 运行

Python 3.9+ 依赖 `matplotlib`：

```bash
python3 python/plot.py \
  --samples data/simulated_fixed_seed_samples.csv \
  --feature-spec data/simulated_fixed_seed_feature_spec.csv \
  --output-prefix /path/to/output/feature_landscape_python \
  --title "Simulated mixed feature landscape" \
  --dpi 320
```

输出 PNG 与 SVG。

R 4.2+ 只使用 base R：

```bash
Rscript r/plot.R \
  --samples=data/simulated_fixed_seed_samples.csv \
  --feature-spec=data/simulated_fixed_seed_feature_spec.csv \
  --output-prefix=/path/to/output/feature_landscape_r \
  --title="Simulated mixed feature landscape" \
  --dpi=320
```

输出 PNG 与 PDF。

## 布局与解释边界

单图允许 1–60 个 sample、1–16 个 feature；画布随样本数、特征数及标签长度增长，超过边界友好报错。右侧逐特征图例保留各 continuous 的显式域、各 categorical/binary 的完整水平映射和缺失编码。

矩阵只显示输入值及缺失状态。颜色相近、共同缺失、样本相邻或特征并列不表示临床关联、风险、机制或因果关系；任何分组、推断或缺失机制解释必须来自上游分析。
