# A 实施接口：O03 / O10 / O11 / O12

依据：当前 PRD 与 v1.6.0 的 Feedback/TaskAssessment/RunGroupPlan/RunBundle；沿用已实现的 lineage、outcomes 和不可变存储。本文件是实施交接，不改产品代码。覆盖全部四项义务，不建设服务、注册器或 rubric DSL。

## 普通函数与消费者

| 模块/API | 输入与返回 | 实际消费者 |
| --- | --- | --- |
| `feedback.freeze_feedback_plan(store, subject, protocol)` | 验证并保存冻结标准、聚合规则、来源与请求身份，返回 plan | sampling；C 的 comparison |
| `feedback.assess(store, plan_id, execution, case, *, evaluate=None, proxy_model=None)` | 逐标准收集/复用反馈并保存 TaskAssessment；缺依据为 unknown | sampling；C 的 comparison |
| `feedback.aggregate(plan, feedbacks)` | 纯函数；返回 outcome/score、完整标准数、缺失标准、来源集合及分数边界 | Store 校验、报告重建、C 的发布复核 |
| `Store.initialize_project(project_id, *, seed=None, source=None)` | 明确空库或 seed 基线；返回 generation=0 的 active 与 baseline_ref | root 的实验入口；`ensure_project` 空库默认路径 |
| `sampling.prepare_sampling(store, tasks, *, policy, context_policy)` | 保存 batch、groups、输入和稳定阶段身份；不调用 execute | sample_tasks；恢复入口 |
| `sampling.resume_sampling(store, batch_id, execute, evaluate, *, resolutions=None, proxy_model=None)` | 只处理未完成阶段；返回原 batch 的 run/episode/assessment/receipt 与 blocked 项 | sample_tasks 调用它；root 的恢复/实验入口 |
| `Store.remember(..., applicability=None)` | 原样保存显式适用标注，纠正仍追加修订 | root 的事实 selector；学习器不调用 |

`sample_tasks` 保持现有入口，内部 prepare → resume；默认旧单标准调用继续工作。新多标准协议显式选择，不能从已有测试数值暗设权重或阈值。

## O03：反馈计划与聚合

新增 `FeedbackPlan`：`feedback_plan_id, project_id, subject, run_id|null, task_revision|null, evaluated_state_digest|null, protocol_id, protocol_hash, criteria[], aggregation, scoring_policy, visibility, evaluator, proxy, requests[], assessment_id, created_at`。

- `subject={kind:episode|evaluation_request, ref, authority_ref|null, execution_ref|null}`。episode 继续用 lineage；comparison 指向真实 EvaluationPlan/request/return，不能制造 Episode 或 RunGroup。
- `criteria[]={criterion_id, rule, weight?}`；`rule` 是传给具体评价函数的现有任务标准材料。ID 唯一，权重必须显式非负且总和大于 0。
- `aggregation={kind:single_task_outcome|binary_all|weighted_sum, threshold?}`；single 保留旧行为，weighted 必须明确 `[0,1]` 阈值。
- `requests[]={request_id, criterion_id, feedback_id}` 与 `assessment_id` 在调用前固定；恢复不靠扫描选一个较好反馈。
- `evaluator={id,config}`；`proxy=null|{enabled:true, model_config, prompt_id, prompt_digest, limits, packet_limits}`。凭据不进记录。
- 每标准沿 `evaluate(request, execution, case)` 调用；request 增加 run_id/criterion_id，case.criteria 是该标准材料，其他任务字段保持。既有单标准第三参数不变。
- 外部返回先保存原文；缺标准、不识别的标准、重复标准及错误身份不被选优或算通过。原文可存，只有匹配 subject/run/state/revision/plan 的条目可参与聚合。
- 二值：所有必需标准 pass 才为 1；任一已绑定可信 fail 即为 0；其余存在 unknown 时整体 unknown/score=null。已知失败与缺项同时保留，0 不表示标准已完整执行。
- 加权：完整已知时 `sum(weight*score)/sum(all planned weights)`；任何缺失均不缩分母，整体 unknown/score=null。
- 加权缺失另给 `[known_weighted_sum/W, (known_weighted_sum+unknown_weight)/W]`，仅描述边界，不能代替已测分数。
- TaskAssessment 引用所有实际反馈及冻结计划，并保存 `expected_criterion_ids, missing_criterion_ids, criterion_coverage, score_bounds, feedback_sources`；旧单标准同样消费这套聚合。
- 不为没调用/没收到的标准制造外部评分。缺失由 plan 与 assessment 的差集表示；实际异常返回可保存 evaluator_status=error 的 Feedback。
- 后来的人工更正/反馈追加，不覆盖原反馈或原 RunBundle.assessment_ref；重算产生新的 assessment，显式引用前版。验证/发布仍绑定确切 assessment，不暗选最新或最好。

## 代理评价真实接入

- 无外部 evaluate 且冻结协议允许 proxy 时，assess 使用现有有界证据包调用 `proxy_judge_v1`；有外部函数时不因为其判断不理想而偷偷切换代理。
- Root 更新 ProxyJudgement：`criterion_findings[]` 增加每项 `outcome, score`，保留 finding/evidence_refs/unknowns；标准 ID 必须属于计划，不能只给一个整体 outcome 后猜各项结果。
- 主机固定 `source=llm_proxy`。聚合保存来源集合；含 proxy 的结果不能被包装成全 external/human，C 的独立证据门继续检查所有参与标准来源。
- 引用、标准集合与身份属于纯 check，使用已有 StructuredModel 的同一修复/调用预算；所有成功、失败和修复调用计费。
- proxy 输入仅包含允许判分的标准及证据；validation/final 材料仍不能回流到学习。没有可用证据/预算时 unknown。

## O10：初始化与发布分开

新增 `BaselineRecord`：`baseline_id, project_id, kind:empty|seed, snapshot_digest, seed_content_hash, source, created_at`。

- seed 接受明确的 `{skills,assets}`；主机将 Skill 所属项目绑定到目标 project，计算完整快照/hash，保留原 seed 内容指纹和显式来源。
- active 增加 `baseline_ref`。空库与 seed 都从 generation=0 开始，`release_id=null`、发布历史为空；初始化不生成 Validation/Release，不声明学习增益。
- `initialize_project` 在项目首次建立基线时完成；同一请求可幂等，已有不同基线或已运行项目不得原地换 seed。需要另一实验臂时使用另一项目。
- `ensure_project` 继续提供默认空库。旧 active 缺 baseline_ref 且能证明是原空库链时可读，不伪造一条历史 seed 初始化记录。
- `_read_active/release_history/_commit_release` 从真实 baseline 起校验链。C 的 promote/rollback 必须认识 baseline 是合法起点，但它不是历史学习发布。
- Root 的实验入口用 seed_content_hash 核对实验臂的初始内容一致；不把项目绑定造成的不同 snapshot digest 误当不同 seed 内容。

## O11：可恢复阶段与未知执行

新计划固定 episode_id、feedback_plan/请求ID、assessment_id、run_id；新增 `CallbackAttempt` 和 `CallbackReturn`，以 attempt_id 连接。

- Attempt：`attempt_id, project_id, batch_id, run_id, stage:execute|evaluate|proxy, request_ref, started_at, config_hash, recovery_ref|null`；调用前原子追加。
- Return：`attempt_id, returned_at, raw_output, error, measured_usage, elapsed_seconds|null`；返回后先持久化，再做轨迹适配、Feedback/Assessment/RunBundle，不能先派生后才保存原返回。
- 新 batch 标记 `recovery_version=1`，说明其 started 日志协议；旧无返回且无 started 的槽位不能推断“从未调用”。
- 已有完整 RunBundle：按身份复用，不执行；已有 raw Return：本地重建缺失 Episode、反馈、assessment、bundle，不重跑 execute。
- 已有 criterion Return/Feedback：复用同一冻结计划的确切结果，不重评；有 assessment 无 bundle 时补 bundle；全部槽位有合法终态后重建原组与原 batch 回执。
- 新日志协议下没有 started 的阶段才可首次调用；有 started 无 return 默认列入 blocked/unknown，不调用外部函数。
- `resolutions[request_ref]` 只接受显式 `attach_result`（原请求的可验证返回材料）、`confirmed_not_executed`（执行方确认未执行及证据）或 `close_unknown`（明确放弃且承认未知副作用）。决定追加记录，不修改原计划/原文。
- `confirmed_not_executed` 才能继续原请求；无法确认却要重新尝试时创建新采样计划并关联原请求，原未知尝试仍入统计，不能悄悄替换为成功。
- `close_unknown` 记录 capture/adapter error 和 underlying termination unknown，不能标 task fail。保留其未知费用与副作用限制；不能把回执闭合说成外部进程已经停止。
- 外部评价/proxy 也有 started/return 记录；丢失返回不能当免费重试。显式重试需新的 attempt、原预算剩余额度和记录原因，第一份有效绑定反馈是本次请求的确定结果，不按分数择优。
- 同 batch 恢复持有本地 batch 锁以避免两个恢复者重复派发；只对本进程/本地文件提供互斥，不声称分布式 exactly-once。
- 旧记录只在身份与内容能唯一关联时补派生结果；重复或不一致记录返回需明确处置，不选最新/最好。

## O12：报告交接与存储增补

- 登记 root 已确定的 `stage_measurements` kind；实际本地 prepare/聚合/保存/恢复段使用 `telemetry.measure_stage`，不把等待并行回调的整个时长算成本地处理时间。
- 每次 sample/resume 的运行段存 `SamplingSegment={segment_id,batch_id,started_at,finished_at|null,elapsed_seconds|null,status,started_attempt_ids,completed_attempt_ids}`。
- `SamplingBatchReceipt` 保存 batch_id、原 group_ids、receipt_refs、segments、first_started_at、finished_at、端到端 span、已测 segment 时长和缺失段数；硬中断的段不补成 0。
- 端到端日历跨度、恢复期间停机、各 callback 时长之和、并行墙钟是不同指标；report 不能相加成一种耗时。
- callback/proxy 的 usage 使用现有唯一 usage_id、exclusive_stage、purpose、run/request/attempt 身份与原测量；重建不重复计已有调用，恢复的本地处理仍记录实际新增时间。
- 计数分别保留独立 task、计划 slot/run、callback attempt、恢复请求；有 started 无 return 的耗时/token/费用未知，完整成本不能假装完整。

Root Schema 增补：FeedbackPlan、BaselineRecord、CallbackAttempt、CallbackReturn、RecoveryResolution、SamplingSegment、SamplingBatchReceipt；现有 Feedback 增 feedback_plan_ref/request_ref/attempt_ref，TaskAssessment 增计划/覆盖/来源/边界及 supersedes，RunGroupPlan/slots 增稳定阶段ID和recovery_version，RunBundle 增 chosen_attempt_ref，active 增 baseline_ref。字段最终以 root canonical 为准。

Store 新 kind：feedback_plans、callback_attempts、callback_returns、recovery_resolutions、sampling_segments、sampling_batch_receipts、baselines；stage_measurements 由 root 已添加，不重复覆盖。

事实小接口：`remember(..., applicability=None)` 保存 `task_ids/task_families/query_terms/global` 的显式标注，旧记录可读；root 负责 relevance selector。此接口仍只接明确用户写入，不能从 reward 改写事实。

## 跨模块验收与边界

多标准缺项不改分母、重复/错绑定不入聚合、proxy标签不可升格；两种baseline跑同一sample→learn→compare→publish；在各持久化边界注入中断并恢复，证明外部调用不重复、原身份不变；未知执行阻止重跑但可显式解决；callback用量不双计、并行批次墙钟独立报告。所有这些必须有实际消费者和测试，不留为“增强项”。只在本任务认可接口后实施；无真实模型、网络、benchmark、提交或产品改动发生在本调查阶段。
