# 项目总纲：执行入口

自动生成，勿独立编辑。版本 1.5.0；源 SHA-256：cfb5c34e4077c0adad846fdccd49cefbbc29e852ecb7b91314299579021ff085。

目标：参考已有论文与源码，从现成 Agent 的执行经历积累经验，生成和演化 Skill，并以版本化方式检查、发布和复用。

目标契约与实现证据分别列出；节点实现标注不代表学习收益。当前工作许可见下方本轮范围。

权威源：docs/blueprint/project-contract.json；阅读视图：docs/blueprint/index.html。

## 本轮范围与工作许可

Python 记忆演化核心参考实现：M1–M3 已落地，检查与效果证据分开；具体客户端暂缓

**产品实现已获授权：implementation_allowed=true。是否已完成以节点证据为准。**

本轮保留：
- 普通事实记忆
- 已有经历导入
- 系统组织单例/同题重复/跨题/批次学习
- 长轨迹/反馈/反例/归因
- Skill 生成和受限演化
- 多候选与关系辅助选择
- 比较协议、版本选择、发布回退、复用与成本

暂缓／不做：
- Codex/Claude 具体适配
- 记忆操作 CLI
- MCP/插件
- 原生会话自动采集
- 项目目录 Skill 同步
- 旧 TS 重建、迁移或删除
- 未声明预算的 benchmark 与推送

需要调用方提供：
- 调用方提供实际任务执行函数；系统决定采样计划并完整记录请求和结果。
- 调用方提供真实评分依据或评价函数；系统固定比较对象/协议、汇总结果、决定采用。
- 已有经历可不具备源快照/上下文/反馈；缺失影响结论，不阻止记录。

范围来源：2026-09-18 用户在就绪核查后明确“继续吧”；沿用已审查的记忆核心范围。

逐项保留 28 个用户问题（按对话重述编号，不冒充原始编号清单）；5 个提示词契约与 18 个结构定义。当前均须区分设计与实现证据。

阅读路线：HTML 的“逐项问题”核对遗漏 → “执行与评价”明确并行、反馈与发布 → “节点契约”按需展开提示词、schema 和说明性示例。

## 节点目录

| ID | 节点 | 职责归属 | 契约 |
| --- | --- | --- | --- |
| N01 | 任务或已有经历入口 | 记忆系统 | Receive : TaskSource → (TaskSpec?, EpisodeRecord?) |
| N02 | 记忆召回、版本与 Skill 选择 | 记忆系统 | Select : (TaskSpec, LibrarySnapshot, UserProjectMemory, PolicyConfig) → ContextManifest |
| N03 | 按计划调用任务执行函数 | 记忆系统 | Sample : (TaskSpec, ContextManifest, PolicyConfig, execute) → (RunGroupPlan, RunBundle[], GroupReceipt, EpisodeRecord[]) |
| N04 | 目标与轨迹索引 | 记忆系统 | Index : (EpisodeRecord[], ContextManifest?) → EpisodeIndex |
| N05 | 反馈接收、获取与结果解释 | 记忆系统 | Feedback : (EpisodeRecord, EvalProtocol?, evaluate?) → (Feedback[], TaskAssessment?) |
| N06 | 经验提炼与归集 | 记忆系统 | Extract : (EpisodeIndex[], Feedback[], M, PolicyConfig) → (EvidencePacket[], ExtractionResult, ExperienceItem[]) |
| N07 | 归因与修改目标 | 记忆系统 | Diagnose : (Experience, Evidence, SourceContext?, S_base, Relations) → ChangeIntent |
| N08 | Skill 生成与演化 | 记忆系统 | Propose_m : (S_base, ChangeIntent, PolicyConfig) → Δ[1..m]; Apply(S_base, Δ_i) → S_candidate_i |
| N09 | 组织候选比较与准入判定 | 记忆系统 | Compare : (S_base, Candidates, Cases, EvalProtocol, execute/evaluate) → (EvaluationPlan, EvaluationResult[], ValidationRecord) |
| N10 | 版本发布与回退 | 记忆系统 | Publish : (Active, Candidate, ValidationRecord, SelectionRecord) → (LibrarySnapshot, ReleaseRecord) |
| N11 | 记录与结果报告 | 记忆系统 | Report : (Episodes, SamplingPlans?, Evaluations, Releases, Usage) → Report |

职责详情见节点 responsibility；provided_function 是调用方提供的操作，与具体客户端适配分开。

## 评价规则与待定参数

- 评价形式与准入规则分开；比较计划先固定，再执行，不按看到的结果改阈值。
- 比较绑定确切 base/candidate、案例集合、评价函数及配置和政策身份。
- 重复数与候选数显式给定；记录全部分配请求，失败/异常/unknown 不被筛掉。
- 回归、稳定性、成本和适用范围有明确检查；单次最好结果不能代替整体。
- 被反复用于选候选的集合不是最终未见测试；验证期间不写回被测记忆。
- 生成经验或候选不等于发布。缺评价条件可保存候选；发布不得以代理自评分冒充独立效果证据。
- 参数 采样和评价重复次数（selected_before_run）：正整数，按目的/预算选择并记录；不存在因 CLI 被取消而生效的默认 1 次。
- 参数 比较范围与任务集合（selected_before_run）：显式说明局部修复、同类迁移或成本优化；相应选择 target/regression/transfer，缺项如实记录，不扩大结论。
- 参数 质量/回归/稳定性/成本门槛（selected_before_run）：用明确准入函数/规则和配置身份固定；不能在结果出来后另找通过理由。
- 参数 多候选选择规则（selected_before_run）：从同一 base 比较，预先固定排序/取舍，失败候选成本入账；单独通过的补丁不自动组合。
- 参数 提取输出与补读预算（selected_before_run）：有效条数/请求/补读/累计输入限制同时给模型和宿主；基础 schema 只定义形状，不能隐藏一个不可见默认上限。

历史数值仅供追溯，不自动成为默认值；详见 runtime.evaluation_policy.historical_examples。


## 固定边界

- I01 实现完整机制的最小版本；不以先证明项目必要性作为开工前提。
- I02 working memory、模型权重和原生工具循环归执行器；用户事实不由 Skill 效果分数擅自改写。
- I03 反馈绑定有效要求及被测状态；任务取消不是失败，后来的要求不追溯约束旧操作。
- I04 观察、评价、原因假设分开；proxy 与 unknown 不升级为真值。
- I05 原始采集记录只追加；派生标注可修订；缺失不由摘要补造。
- I06 经验池 M、版本归档 V、active 指针 a 分开；入池或生成候选不等于发布。
- I07 修改仅允许显式列出的操作，带目标与基础版本；NOOP 不改变 active。
- I08 只有 N10 可以写 active_pointer；发布须关联通过的检查、匹配的基础版本及完整资产。
- I09 每次运行固定 library snapshot；发布或回退只影响后续运行。
- I10 选择 active 库版本与按任务选库内 Skill 是两个决策。
- I11 依赖、声明冲突、共同使用、测得影响分开；组合消融不破坏必要依赖。
- I12 在线先测当前题再更新；冻结测试不更新；计入提炼、失败候选、验证和补救，未来答案不前泄。
- I13 运行时学习器不改 Trellis 规范、开发指令或消费者全局配置。
- I14 实现任务绑定总纲版本/节点/范围；中断后先读检查点；用户新要求通过明确修订更新契约。
- I15 新采样/比较固定任务、状态、库与协议，并保留全部计划结果；已有经历导入不伪造运行计划。逐题与微批更新时机明确。
- I16 检查记录绑定完整 candidate/base/config/protocol/data；发布使用 compare-and-swap，不自动发布未验证 rebase。
- I17 结构合法仅代表格式可解析；引用、状态绑定、语义支撑和外部效果分别验证。

## 中断后恢复

- 当前交付范围、implementation_allowed 与节点实际证据
- 当前 Python 实施任务 resume.md 与 M1–M3 检查点
- 对应 Q/N 的职责、输入输出和评价协议
- 必要的 schema/示例；历史参考配置不自动生效
- 按需读取原论文及历史，不用旧 in_progress 字段恢复代码

按需读取节点：node docs/blueprint/build.mjs node N08。默认读取步骤、提示词和结构索引；确需完整 schema/示例时追加 --full。只加载当前节点和相关代码，不默认重读全部文献。

用户的新要求可以修订总纲；先记录影响的节点与版本，不能用旧总纲拒绝明确的新方向。
