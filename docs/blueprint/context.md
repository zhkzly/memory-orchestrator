# 项目总纲：执行入口

自动生成，勿独立编辑。版本 1.6.0；源 SHA-256：129ba6c47f740b9f58a4642c04c8e7ed0e1e7ca3811f1503f8ae52e703520cc7。

目标：参考已有论文与源码，从现成 Agent 的执行经历积累经验，生成和演化 Skill，并以版本化方式检查、发布和复用。

目标契约与实现证据分别列出；节点实现标注不代表学习收益。当前工作许可见下方本轮范围。

权威源：docs/blueprint/project-contract.json；阅读视图：docs/blueprint/index.html。

## 本轮范围与工作许可

保持 Python 记忆演化主线，修正事实绑定、闭合、证据交接与统计粒度；未实现设计能力逐项保留

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

范围来源：2026-09-18 用户明确要求从根源修改，避免逐症状打补丁；继续保留既定核心与客户端暂缓边界。

逐项保留 28 个用户问题（按对话重述编号，不冒充原始编号清单）；5 个提示词契约与 19 个结构定义。当前均须区分设计与实现证据。

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

## 当前实现覆盖

机制、行为证据和效果证据分别记录；文件存在与测试通过不能推导全部义务完成。

- N01 [partial] 事实追加与纠正、已有经历导入、已知来源一致性检查；未知外部来源可保留。 待完成：标准 seed 初始实验臂尚未接通。效果：未获得 benchmark、未见任务或净维护收益证据；构造测试仅证明被覆盖的行为。
- N02 [partial] 固定快照、词法选择、依赖闭包、声明冲突与字符预算；提供清单和关系加权已接通。 待完成：关系适用上下文/源版本筛选未接通；事实选择以项目和预算为主，尚无任务相关性选择。效果：未获得 benchmark、未见任务或净维护收益证据；构造测试仅证明被覆盖的行为。
- N03 [partial] 先冻结批次成员、同题槽位和评分政策，再有限并行执行；学习检查实际组/批次闭合，保留部分轨迹和初态矛盾。 待完成：进程中断后未闭合组的恢复尚未实现。效果：未获得 benchmark、未见任务或净维护收益证据；构造测试仅证明被覆盖的行为。
- N04 [partial] 显式目标修订、调用/父子关系与原字节索引；有界投影保留已知结构、可见关系和不确定性。 待完成：尚未实现流式索引和文件/共享产物依赖链回找；自动目标绑定提示词尚未接入学习流程。效果：未获得 benchmark、未见任务或净维护收益证据；构造测试仅证明被覆盖的行为。
- N05 [partial] 反馈追加绑定已知 run/产物/项目/修订；终态与任务结果分开，单 task_outcome 形成 TaskAssessment。 待完成：多标准/加权 TaskAssessment 聚合未接通；代理判分提示词尚未接入自动路径。效果：未获得 benchmark、未见任务或净维护收益证据；构造测试仅证明被覆盖的行为。
- N06 [partial] 有界证据与补读、引用验证、弃权、精确去重、历史边界保留和相关经验检索；学习前校验来源用途与闭合。 待完成：专门的失败签名定向检索尚未接通。效果：未获得 benchmark、未见任务或净维护收益证据；构造测试仅证明被覆盖的行为。
- N07 [partial] 以可见经验/证据生成原因假设、替代解释和修改路由，校验既有目标并在预算内修复。 待完成：check_plan 只记录和传递，没有自动转为区分性/最小组合实验。效果：未获得 benchmark、未见任务或净维护收益证据；构造测试仅证明被覆盖的行为。
- N08 [partial] ADD/PATCH/RETIRE/NOOP、规则/路径/所有者/资产/依赖约束已接通；提案尝试保留，比较按唯一快照进行。 待完成：附属脚本只有文本/hash与结构检查，未自动编译或执行资产测试。效果：未获得 benchmark、未见任务或净维护收益证据；构造测试仅证明被覆盖的行为。
- N09 [partial] 比较前固定对象、请求、评分政策和准入门；按唯一快照复测，保留全部提案别名，选择绑定完整冻结集合。 待完成：诊断 check_plan 和关系定向组合实验尚未接通。效果：未获得 benchmark、未见任务或净维护收益证据；构造测试仅证明被覆盖的行为。
- N10 [implemented] 重新核对存储中的计划/结果/验证/选择，按确切快照及提案别名发布；CAS、代次、幂等和历史回退已接通。 待完成：本节点列明的机制暂无待实现项。效果：未获得 benchmark、未见任务或净维护收益证据；构造测试仅证明被覆盖的行为。
- N11 [partial] 从计划与原始结果计量，验证决定单列；采样按权威 assessment 汇总，按用途/模式/终态分报，唯一快照与提案/验证尝试分开。 待完成：整组墙钟时间与全部维护环节成本采集尚未覆盖；Skill 增长和关系效果的完整纵向指标尚未接通。效果：未获得 benchmark、未见任务或净维护收益证据；构造测试仅证明被覆盖的行为。

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
- 架构 resume.md 与最近修复任务的验收记录；归档 M1–M3 仅作历史
- 对应 Q/N 的职责、输入输出和评价协议
- 必要的 schema/示例；历史参考配置不自动生效
- 按需读取原论文及历史，不用旧 in_progress 字段恢复代码

按需读取节点：node docs/blueprint/build.mjs node N08。默认读取步骤、提示词和结构索引；确需完整 schema/示例时追加 --full。只加载当前节点和相关代码，不默认重读全部文献。

用户的新要求可以修订总纲；先记录影响的节点与版本，不能用旧总纲拒绝明确的新方向。
