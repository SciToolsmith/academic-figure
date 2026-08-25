# Subject timeline / swimmer plot 通用模板

这是 `rf-0026` 的去案例化 Python/R 双实现。每个 subject 占一条横向时间轨；有色区间表示已提供的阶段，可选事件用形状和颜色叠加。模板不计算生存概率、风险、显著性或因果效应；横向位置只表示用户提供的时间顺序。

## 数据契约

五张 CSV 的外键关系是：

```text
subjects.subject_id
  ├─ intervals.subject_id
  └─ events.subject_id       (可选)

interval_types.interval_type ─ intervals.interval_type
event_types.event_type       ─ events.event_type
```

### `subjects`

| 字段 | 要求 |
|---|---|
| `subject_id` | 必需、非空、全表唯一；是 intervals/events 的唯一合法外键集合 |
| `subject_label` | 必需、非空；绘图时与 ID 一起显示，不用标签代替 ID |
| `display_order` | 必需、正整数、唯一；显式控制单页顺序，也可供用户在上游分批 |
| `observation_start`, `observation_end` | 有限数值且 `start < end`；所有区间和事件必须落在闭区间内 |
| `time_unit` | 必需、非空；本模板的单个输出只允许一个完全相同的单位，不自动换算 |

### `intervals`

`interval_id` 全表唯一；`subject_id` 必须存在；`start`/`end` 必须有限且 `start < end`；`interval_type` 必须存在于 `interval_types`；`time_unit` 必须与 subject 相同。同一 subject 的行必须按 `start` 非递减出现，且区间不重叠；模板不会暗中排序、合并或裁剪。需要并行轨道时应改用明确的多轨数据契约。每个 subject 至少有一个区间。

### 可选 `events`

`event_id` 全表唯一；`subject_id` 必须存在；`time` 必须有限并位于 subject 观察边界内；`time_unit` 必须相同。同一 subject 的事件行必须按时间非递减出现。`event_type` 必须在 `event_types` 字典中显式声明；未知类型会终止绘图，不会被默认成“other”、普通圆点或某个颜色。

### 类型字典

- `interval_types`: `interval_type`, 非空图例文本 `interval_type_label`, `#RRGGBB` 颜色。
- `event_types`: `event_type`, 非空图例文本 `event_type_label`, marker 和 `#RRGGBB` 颜色。marker 仅允许 `circle`、`diamond`、`triangle`、`square`、`cross`，以便 Python/R 显示一致。

未列出的额外列不参与绘图。脚本对无效记录整体失败，不静默删行、去重或用演示数据替换真实输入。

## 演示数据

`data/simulated_fixed_seed_*.csv` 是中性模拟数据，由固定伪随机种子 `26` 生成。三张观测表的 `data_status=SIMULATED` 和 `simulation_seed=26` 明确标记来源；脚本还会检查这些标记在文件内及文件之间一致。对象名、阶段和事件均不代表临床、生物学或其他领域结论。

## 运行

Python 3.9+ 依赖 `matplotlib`：

```bash
python3 python/plot.py \
  --subjects data/simulated_fixed_seed_subjects.csv \
  --intervals data/simulated_fixed_seed_intervals.csv \
  --events data/simulated_fixed_seed_events.csv \
  --interval-styles data/interval_types.csv \
  --event-styles data/event_types.csv \
  --output-prefix /path/to/output/timeline_python \
  --title "Simulated subject timelines" \
  --dpi 320
```

输出 PNG 与 SVG。

R 4.2+ 只使用 base R：

```bash
Rscript r/plot.R \
  --subjects=data/simulated_fixed_seed_subjects.csv \
  --intervals=data/simulated_fixed_seed_intervals.csv \
  --events=data/simulated_fixed_seed_events.csv \
  --interval-styles=data/interval_types.csv \
  --event-styles=data/event_types.csv \
  --output-prefix=/path/to/output/timeline_r \
  --title="Simulated subject timelines" \
  --dpi=320
```

输出 PNG 与 PDF。不需要 events 时省略 `--events` 和 `--event-styles`。

验证预览：[Python](../../assets/open-templates/rf-0026/preview-python.png) · [R](../../assets/open-templates/rf-0026/preview-r.png)

## 自适应布局与分页

- 画布高度随 subject 数增长；宽度随最长 subject/类型标签和事件类型数增长，不靠把字体压到不可读来容纳数据。
- 脚本的单页硬上限是 36 个 subject。超过时整批停止并给出友好错误，不自动分页、不截断或抽样。请在上游按 `display_order` 连续分批，或按预先声明的科学分组分别运行脚本；每批仍需提供完整且自洽的 subjects/intervals/events 外键集合。
- 图例依类型数自动分列/分行；颜色不是唯一编码，事件同时使用形状。

36 是可读性边界，不代表科学分组。分批输出之间若需要科学比较，应由用户先定义分组、排序和不可分割单元，并在图注中说明分批规则。

## 解释边界

图形只显示输入中已记录的区间和事件。时间先后、区间长度、事件共现或行排序都不自动表示因果、机制、生存或风险差异。如果 observation end 含有删失、失访、当前仍进行或特定终点语义，必须在上游将其显式建模，不能从轨道终点外观推断。
