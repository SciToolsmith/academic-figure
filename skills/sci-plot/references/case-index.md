# 案例索引

用案例学习“如何表达证据”，不要照着图形名称套模板，也不要复制原案例脚本。案例只是优先参考，不是能力边界：即使没有任何案例，skill 也应根据 Figure Contract 与图形语法完成原创设计。先确定科学问题、观测单位和数据结构，再决定是否检索案例。

## 三个彼此独立的状态

- **`audit_status`**：科学表达审计状态。`admitted` 可作为正向参考；
  `conditional` 必须先满足 `repair_gate`；`inspiration` 和
  `quarantined` 只返回阻断原因，不作为生产参考。
- **`implementation_status`**：实现证据状态。`verified`、
  `language-specific`、`static-reviewed`、`unreviewed` 和 `failed`
  只描述该逻辑案例在原项目审计时的实现检查深度，不替代科学审计，也不表示
  当前随 skill 打包的 Python/R 两个入口及缺失输入都已生产验证。
- **`reuse_level`**：当前任务的复用方式：`exact`、`structural`、
  `style-only` 或 `build-new`。它由本次 Figure Contract 决定，不写入
  案例目录。

“复用”首先指复用设计决策，不代表复制数据或结论。18 个案例现在也各自附带
Python 与 R 的作者复现源码，但它们属于独立的“参考源码层”，不是自动可运行
的生产模板；论文原始数据没有随 skill 分发。需要查看或适配源码时，继续读取
[case-code.md](case-code.md)。

## 检索顺序

1. 写出一句科学问题和预期读者结论。
2. 识别观测单位、独立性、配对/重复测量、时间、空间、集合或网络关系。
3. 选择证据角色：展示原始数据、估计量、不确定性、模型诊断、组成、流向或多证据整合。
4. 从下表选择一个主案例；只有主案例不能覆盖次要面板时，才选择一个辅助案例。
5. 检查对应卡片的禁用条件和已知风险。
6. 若没有语义匹配，记录 `retrieval_status: no-suitable-case` 与
   `reuse_level: build-new`，立即从 Figure Contract 与图形语法继续原创设计。

两个离散条件或时间点、且核心证据是对象内变化时，优先按 `paired` 检索；
多时间点轨迹、时间趋势或过程形状才优先按 `repeated-measures` /
`longitudinal` 检索。名称不能替代对独立性和目标估计量的判断。

## 正向案例总览

| 层级 | ID | 科学表达决策 | 典型数据结构 | 主要证据角色 | 审计 / 实现状态 |
|---|---|---|---|---|---|
| 核心 | `rf-0104` | 同时展示分布形状、原始观测和稳健摘要 | 独立分组连续变量 | 分布与样本量 | `conditional` / `static-reviewed` |
| 核心 | `rf-0173` | 保留对象级配对变化，而非只比较边际分布 | 宽表或长表配对/重复测量 | 个体变化与配对估计 | `conditional` / `static-reviewed` |
| 核心 | `rf-0088` | 对齐效应量、区间和变量表 | 预计算回归结果表 | 调整后效应估计 | `conditional` / `static-reviewed` |
| 核心 | `rf-0178` | 把拟合、边缘分布和残差诊断组成证据链 | 连续变量、分组、模型残差 | 关系、估计与诊断 | `admitted` / `verified` |
| 核心 | `rf-0180` | 显式呈现双轴非对称测量不确定性 | 点估计及上下误差 | 不确定性与分层 | `conditional` / `static-reviewed` |
| 核心 | `rf-0109` | 在同一行对齐排名、分数、缺失值和配置 | 方法 × 指标异构矩阵 | 方法比较 | `admitted` / `verified` |
| 核心 | `rf-0102` | 将相关结构与聚类决策绑定解释 | 变量 × 观测矩阵 | 相关模块与层级 | `conditional` / `static-reviewed` |
| 核心 | `rf-0018` | 联合呈现时间结局、删失、风险人数和效应 | 个体随访时间、状态、组别 | 生存概率与组间比较 | `admitted` / `verified` |
| 核心 | `rf-0061` | 同时保留个体轨迹和组级时间趋势 | 个体 × 时间重复测量 | 动态过程与异质性 | `admitted` / `language-specific` |
| 核心 | `rf-0001` | 在共同分母下比较组成变化 | 组别 × 类别计数/比例 | 组成结构 | `admitted` / `verified` |
| 核心 | `rf-0157` | 区分精确交集、集合规模和筛选长尾 | 对象 × 集合成员关系 | 精确集合交集 | `conditional` / `verified` |
| 核心 | `rf-0107` | 从特征级差异连接到通路级富集 | 差异统计表、排序向量、基因集 | 多层组学证据链 | `conditional` / `static-reviewed` |
| 扩展 | `rf-0054` | 对齐聚类模式、代表特征和功能注释 | 表达矩阵、簇分配、富集结果 | 模块解释 | `conditional` / `static-reviewed` |
| 扩展 | `rf-0063` | 让异构临床轨道共享同一患者顺序 | 患者 × 多类型特征 | 个体异质性 | `conditional` / `static-reviewed` |
| 扩展 | `rf-0035` | 沿统一时间轴表达对象历程和离散事件 | 对象级起止时间与事件 | 患者/对象过程 | `conditional` / `static-reviewed` |
| 扩展 | `rf-0176` | 展示已有低维坐标，不暗示重新计算嵌入 | 对象坐标与类别标签 | 高维结构的二维视图 | `conditional` / `static-reviewed` |
| 扩展 | `rf-0118` | 以流带表达多阶段转换并明确带宽语义 | 阶段间类别转换或加权边 | 流向与规模 | `conditional` / `static-reviewed` |
| 扩展 | `rf-0159` | 在明确 CRS 和边界版本下表达空间差异 | 经纬度/区域值与空间几何 | 空间梯度与热点 | `conditional` / `static-reviewed` |

读取 [cases-core.md](cases-core.md) 获取 12 个核心案例卡，读取 [cases-extensions.md](cases-extensions.md) 获取领域扩展卡。遇到统计语义或视觉诚实性风险时，读取 [risk-cards.md](risk-cards.md)。

机器检索使用 [case-index.json](case-index.json)，中英文别名及变换守卫词
集中在 [retrieval-lexicon.json](retrieval-lexicon.json)。它只帮助缩小候选，
不决定最终图形。检索器会返回 `matched`、`repair-required-only` 或
`no-suitable-case`。后两种状态都允许直接按
[figure-grammar.md](figure-grammar.md) 原创设计；不能为了避免空结果而降低
科学语义门槛。显式结构或领域约束只能过滤候选，不能抬高语义相关分；
低于阈值的条目只会出现在 `constraint_only_candidates` 中，供澄清或人工
审阅，不能作为匹配案例复用。

源码资产清单见 [case-assets.json](case-assets.json)。它记录每个案例的 Python/R
入口、所需输入、预览证据、来源、许可和冒烟状态。源码清单不参与语义排名，
避免“有代码”反过来影响科学选择。

## 使用限制

- 每个任务默认只加载一个主案例和至多一个辅助案例，不要一次加载全部案例。
- 不把案例标题当作统计方法；先验证方法是否适合当前设计。
- 不把 Python/R 文件名相似视为结果等价；分别记录每种实现的状态。
- 不把脚本成功运行视为图形正确；验证数值、语义、版式和导出产物。
- 不把存在源码误读为数据也已打包；多数案例需要用户提供或重新映射输入。
- 不在 skill 目录原地运行案例源码；只在独立暂存目录中检查和适配。
- 不把一个目录视为一个逻辑图件；多变体案例应在图件级、语言级登记状态。
- 不因案例库无匹配项而强行选择相近图形。
