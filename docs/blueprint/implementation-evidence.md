# 完整 Python 记忆演化实现证据

本页对应总纲 v1.7.0 的既定机制。用户要求完整实现；原 K01–K14、Q01–Q28、N01–N11 均保留。具体 Codex/Claude 适配、CLI/MCP 和目录同步仍按原约定暂缓，旧 TypeScript 和用户数据保留。

调用入口与参数见 [Python 使用说明](../../examples/memory_evolution/README.md)。`evolve()` 组织学习、候选比较、选择与发布；提供方负责实际执行环境和评分依据。核心不要求调用方重写演化决策。

## 逐项义务与消费者

| 义务 | 输入到实际消费者 | 行为证据 |
| --- | --- | --- |
| O01 目标关联 | 缺标用户事件 → 有界窗口/已有目标目录 → 有依据的目标旁注 → 实际提取输入；原始事件不改 | [目标切换/恢复与未知](../../tests/test_memory_goals.py)、[真实学习输入](../../tests/test_memory_learning.py) |
| O02 长轨迹 | JSONL归档 → SQLite增量索引/正文范围 → 有界片段和依赖回找 → 学习器；原始偏移与解码范围分开 | [重开续建、Unicode范围、文件依赖、跨层父来源](../../tests/test_memory_trace.py) |
| O03 反馈 | 执行前冻结准则/权重 → 逐项真实评价或有界代理 → TaskAssessment → 学习、比较和报告；unknown不缩分母 | [二值/加权规则](../../tests/test_memory_feedback.py)、[代理、费用与原计划恢复](../../tests/test_memory_sampling.py) |
| O04 经验维护 | 失败签名检索 → 结构化经验 → 重复/冲突/撤回关系 → 下次检索折叠或保留反例；没有提交的维护不生效 | [实际维护消费](../../tests/test_memory_maintenance.py)、[跨轮检索](../../tests/test_memory_learning.py) |
| O05 Skill必要性 | 已有能力目录/行为差异/证据 → diagnose中的必要性判断 → NOOP/needs_evidence/允许ADD；提案实际受限 | [无差异不提案、禁止ADD的修复、已有能力比较](../../tests/test_memory_learning.py) |
| O06 检查计划 | 诊断与全部提案别名的义务并集 → 可信材料绑定 → 新的实际请求/缺证 → 准入与发布复核 | [追加检查、缺材料、质量集不被稀释](../../tests/test_memory_verification.py)、[发布复核](../../tests/test_memory_release.py) |
| O07 局部关系 | 有限Skill对 → 两个依赖完整视图 → 实际执行/评价 → 有范围/修订的measured_effect → 后续选择 | [真实CSV对照改变selector、错范围排除、不可辨识](../../tests/test_memory_verification.py) |
| O08 附属脚本 | 完整候选脚本/关联资产 → 实际Python编译和可信功能fixture → 检查记录 → 准入/发布 | [语法错、功能错、正确、超时、材料替换](../../tests/test_memory_verification.py) |
| O09 事实记忆 | 用户/项目事实及明确适用范围 → 当前任务相关性/预算选择 → 提供清单；reward无事实写权限 | [无关事实排除](../../tests/test_memory_completion.py)、[事实来源和纠正](../../tests/test_memory_store.py) |
| O10 初始库 | 明确empty/seed → 项目基线/相同内容身份 → 同一采样与演化路径；不记为学到的发布 | [初始化](../../tests/test_memory_store.py)、[三臂同基线](../../tests/test_memory_experiments.py) |
| O11 恢复 | 原计划/started/return → 重建缺失派生产物 → 原ID回执；无返回需有证据的处置，不能盲目再执行 | [采样中断与进程退出](../../tests/test_memory_sampling.py)、[比较/反馈/准入恢复](../../tests/test_memory_comparison_recovery.py) |
| O12 计量 | 实际调用/失败/已报价格 + 本地阶段计时 + 批次运行段 → 唯一用量与未知项报告；未终结学习周期不称完整成本 | [模型传费](../../tests/test_memory_model.py)、[计时](../../tests/test_memory_telemetry.py)、[中断成本](../../tests/test_memory_completion.py) |
| O13 纵向报告 | 已提交版本/回退、维护关系、轨迹和提供/消费/对照记录 → 库增长、规则/资产、检索、冲突、分层消费报告 | [两次发布再回退的实际报告](../../tests/test_memory_completion.py)、[计划分母与逐题结果](../../tests/test_memory_report.py) |
| O14 实验 | 冻结数据/全部配置/seed → 隔离的online/frozen/frozen_microbatch Store → 本题先测后学 → 冻结final → 逐题差异 | [三臂与原配置被外部修改的反例](../../tests/test_memory_experiments.py)、[可运行研究入口](../../examples/memory_evolution/study.py) |
| O15 一致性 | 同源prompt/schema + 全调用预算 + 身份/来源/修订检查 → 每个真实消费者；失败不空成功 | [契约同源与内嵌定义](../../tests/test_memory_contract.py)、[有限格式/语义修复](../../tests/test_memory_model.py) |
| O16 可复核交付 | 原义务 → 实现/反例/独立复核/故障注入 → 本页和生成HTML；效果与机制分开 | 下方检查记录与Trellis任务研究材料 |

## 检查结果

最终全套 **268项通过**；Python编译检查通过。官方故障注入 **68/68被检测**（A18、B20、C18、root12），每项注入前为绿、破坏后为红，恢复后为绿，源码hash精确恢复。总纲结构检查、37项文档负例、6项生成视图检查及内嵌脚本语法通过。

真实SDK接线使用用户配置的 `gpt-5.6-terra`，预算为最多8次调用、每次4000输出token、总输入480000字符、单次超时30秒。本次实际4次调用，已报模型输入23956、输出3791、总计27747 tokens，用时78.40秒；费用未提供，因此未知。完成提取、语义维护、归因和候选生成；候选包含两项未绑定可信材料的必需检查，验证为unknown，**没有发布**。完整证据及原始模型输出保留在本次Trellis验收档案；未修改门槛追求成功发布。另保留了受限网络环境下的连接失败记录。

检查不是只用相同调用链自证：A/B/C互相检查了长轨迹与来源、实际代理/多准则、脚本和关系消费者，B另审查根模块的实验/计量/报告。发现并修正了跨层父来源漏检、同快照义务排序、公开目录混入私有字段、追加检查稀释原质量集、费用字段丢失和可变配置等实际问题。原始反例保留，未通过删除义务或放宽准入来解决。

## 证据边界

- CSV处理、脚本、对照、持久化、恢复和版本切换实际在本机执行；构造教师的决策用于确定性检查，不是测量模型的学习能力。
- 目标关联、语义去重和归因仍是模型判断。协议校验能拒绝假引用/越界/缺证，不能证明自然语言解释为真；准确率需要另设独立标注。
- `measured_effect` 是固定案例与背景下的条件增量，适用范围/版本会参与实际选择。它不证明所有任务上的普遍因果。
- 真实benchmark、未见任务收益和扣除全部维护费用后的净收益未测。缺少价格、缺返回或未终结周期保持unknown。
- 默认Python资产执行器提供进程级限制，不提供OS沙箱；要求的隔离能力不可用就留下unknown。
- 浏览器URL策略仍限制视觉检查；HTML只做源数据、脚本语法与生成一致性检查，不绕过该限制。
