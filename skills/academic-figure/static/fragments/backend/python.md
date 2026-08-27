# Python 路线

根据任务选择最少足够的工具：

- 数据：`pandas`, `numpy`；XLSX 可用 `openpyxl`。
- 绘图：优先 `matplotlib`；统计图可辅以 `seaborn`。
- 标签避让：`adjustText`可选。
- 网络：`networkx`可选；空间：`geopandas`/`cartopy`仅在真正需要时引入。

脚本要求：

- 将用户可调参数放在紧凑的 `CONFIG` 区，不将实际列名、阈值和结论写死在绘图函数中。
- 分离读取/验证、变换、绘图和导出。
- 在绘图副本中处理显示下限或抖动，不修改源数据。
- 大点云使用 rasterization、hexbin、密度或明确的聚合策略，不为速度默默抽样。
- 保存 SVG/PDF 时优先可编辑文字；PNG/TIFF 按最终物理尺寸确定 DPI，不把单独的 `dpi=300` 当成清晰度保证。
- 将字体家族和字号层级放入 `CONFIG`。含 CJK 文字时，用 `matplotlib.font_manager.findfont(..., fallback_to_default=False)` 逐个精确检测候选字体；可优先尝试 `Source Han Sans CN`、`Hiragino Sans GB`，不得把 `DejaVu Sans` 或静默系统回退当作中文主字体。
- 找不到可覆盖实际标签的 CJK 字体时，清楚说明阻塞或选择已验证备用字体；生成后检查 missing-glyph 警告、中文与拉丁/数学符号混排和真实字重。
- 需要可编辑矢量文字时显式设置 `svg.fonttype = "none"`、`pdf.fonttype = 42`；同时说明 SVG 接收端仍需相应字体，必要时另交轮廓版但保留可编辑源。

生成后，用 Python 实际运行脚本并检查输出。如果缺少运行时或依赖，说明阻塞及安装方式，不用 R 偷换生成一张“看起来差不多”的图。
