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

生成后，用 Python 实际运行脚本并检查输出。如果缺少运行时或依赖，说明阻塞及安装方式，不用 R 偷换生成一张“看起来差不多”的图。
