# Research: 并行采样、反馈计分与发布防退化节点审查

- Query: 审查 N01/N03/N05/N09/N11：同题并行如何执行、如何区分重复与独立任务、reward 如何产生并进入提取、如何聚合、如何避免退化及报告完整成本。
- Scope: mixed；只读本地契约/源码与公开论文/冻结源码；只写本报告。
- Date: 2026-09-18
- Contract examined: 1.0.0；source SHA-256 82b0c6aecfd718c352c32d17ca192bd28819bf2011a80b293b1bb0ad20cba4c8。
- Ownership: 本报告不修改总纲、HTML、产品代码、依赖、执行器配置；没有模型调用、benchmark 执行、原生日志读取或私有材料上传。
- Intent: 参考方法实现独立项目；不是复现某一篇论文，也不设置“先证明项目值得做”的开发前置门槛。下文验证是产品内部发布与结果报告的组成部分。

## Findings

### 1. 必须分别保留的问题清单

这些问题不能压缩成一个“支持采样”开关。

| 问题 | 所属节点 | 第一版需要形成的明确决策 |
| --- | --- | --- |
| Q-S01 同一个 task 能否同时执行多次 | N01/N03 | 可以，要求可隔离/可恢复的初态、同一冻结快照、独立运行目录/会话、固定槽位与组屏障 |
| Q-S02 不同 task 能否并行 | N03/N10 | 冻结评测可以；在线学习须说明按题发布还是按批发布，二者统计语义不同 |
| Q-S03 重复几次，是否遇到成功就停 | N03/N09 | 次数与停止规则属于版本化协议；不把“直到成功”输出当作一次成功 |
| Q-S04 多条轨迹怎样进入学习 | N06/N07 | 同题先形成对照组，再与跨题同类证据聚合；保留每条轨迹与反馈身份，不只选赢家 |
| Q-S05 reward 究竟从哪里来 | N05 | 任务验收器/环境、人工、LLM proxy 分开；reward 是反馈的派生数值，不是事实、诊断、经验的同义词 |
| Q-S06 如何避免随机成功误导 | N09/N11 | 全部重复结果、观测覆盖率、任务数、单次均值与所选结果分报；不以 best-of-k 代替单次质量 |
| Q-S07 如何证明修改没有破坏旧能力 | N09 | 基线/候选成对执行、目标与回归分层、逐题救回/回归、关键约束硬门槛、证据不足返回 unknown |
| Q-S08 训练、发布与最终报告用什么数据 | N01/N05/N09/N11 | 学习集、发布选择集、最终冻结集分离；重复用来选候选的“留出”不是最终未见测试 |
| Q-S09 多次采样和验证是否值得成本 | N11 | 记录执行、提炼、提案、失败候选、验证、选择、补救全部成本；并行墙钟时间与总资源用量分开 |
| Q-S10 候选很多、发布很多会不会慢慢退化 | N09/N10 | 固定候选预算和比较协议；只允许单一发布器更新 active；保留稳定锚点与回退，不累积无限容忍的小退化 |

### 2. 当前契约的真实缺口

当前 v1 的职责方向基本正确，问题主要在“可执行的数据和判定规则仍是概括性文字”。以下不是说这些能力已实现。

| 位置 | 已有内容 | 实现前仍缺的内容 |
| --- | --- | --- |
| docs/blueprint/project-contract.json:108，K06 | 单例、同题重复、跨题案例、反例分别有名 | K06 只关联 N06/N07/N09，没有把实际调度责任落到 N03；重复的组标识、槽位、数目与完成屏障未定义 |
| 同文件:201，TaskSpec；:293，N01 | task/goal revision、环境引用、可重放初态 | 环境快照摘要、可隔离能力、是否可复制外部副作用、允许的初态复位方式、任务 family/template 标识 |
| 同文件:211，PolicyConfig | “采样策略、重复次数、候选数”是字段说明字符串 | repeats 与 concurrency 是不同变量；同题/跨题执行模式、停止规则、槽位异常策略、在线更新时刻未定 |
| 同文件:231，RunBundle；:362，N03 | 固定模型、预算、工作区与 Skill 快照 | sample_group_id、slot_id、环境实例身份、实际 seed 支持状态、执行状态、反馈状态、前序依赖、各运行隔离证据 |
| 同文件:241，Feedback；:433，N05 | pass/fail/unknown、来源、被测状态、时间 | criterion 级结果数组、可选数值及量纲/上下界、评价器版本、反馈权限、未知原因和任务级聚合函数 |
| 同文件:216，EvalProtocol | online_or_frozen、split、scoring、unknown_policy | 每种反馈可被 actor/extractor/proposer/selector 看见的权限；学习/发布/最终冻结的材料集合与内容哈希 |
| 同文件:588，N09 | 全部重复、质量/稳定性/回归/成本、unknown 不通过 | 基线与候选成对计划、分母、最小证据、容忍差、关键能力门槛、缓存基线可复用条件、选择次数上限 |
| 同文件:271，ValidationRecord | per_task_runs、accepted/rejected/unknown | 完整 planned slots、遗漏与替补记录、成对差值、未决原因、每个门槛的测量值与阈值 |
| 同文件:669，N11 | 任务/执行分母、异常/未知、全成本 | macro task mean、best-of-k/selector yield、coverage、未知上下界、稳定性统计、在线流的统计单位 |
| 同文件:629，N10 | 唯一发布器、base 匹配、旧快照与回退 | 现有规则足够作为并发基础；应明确同 base 多个候选只能选一个，组合补丁要重新验证 |

当前产品也没有可复用的任务效果验收器：src/core.ts:209 的 verifyCandidate 主要根据 evidence 数量决定 verified；src/controller.ts:550 的 evaluateProposal 根据目标、风险和可逆性打结构分；src/types.ts:1 仍是四种原型 MemoryKind。这些行为不能直接换名当作 N05 或 N09。

### 3. 论文与代码实际做了什么

证据区分：P = 论文报告；C = 固定提交静态源码；O = 本项目拟议选择。没有在本轮重现作者结果。

#### 3.1 ReasoningBank / MaTTS

P：并行 MaTTS 对同一 query 生成多条轨迹，比较成功与失败中的模式后提炼；顺序 MaTTS 是完成后的继续 re-check。它们不是多位 reviewer 阅读同一条日志。论文区分随机选择一条轨迹的 Pass@1 与模型选择的 Best-of-N；后者并非隐藏答案提供的 oracle 选择。[论文 §3.3、§4.3–4.4、A.3](https://arxiv.org/html/2509.25140v2)

C：pipeline_scaling.py:37–78 对一个任务启动多个 Popen，设置不同环境端口与 results_i，等待全部结束才提炼，然后进入下一 task；这是我们“同题并行、任务间设屏障”结构的直接参考。[冻结流水线](https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/WebArena/pipeline_scaling.py#L37)

C：PARALLEL_SI 要求对照多条轨迹、避免重复，合计至多 5 项；每项由 Title、Description、Content 组成，Description 包含适用/不适用情况。这个输出结构没有本项目要求的 evidence event ID、反证引用和已验证原因等级，需自行补上。[冻结提示词](https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/WebArena/prompts/memory_instruction.py#L63)

P：作者报告 Shopping judge 对 gold 的准确率为 72.7%；检索经验数量从 1 增至 4 时，所报成功率由 49.7 降到 44.4。前者提醒 proxy 不是真值，后者提醒增加记忆不保证更好。普通流程将新经验直接追加，未提供本项目的逐候选发布回归门。[论文 §5、A.2、C.1](https://arxiv.org/html/2509.25140v2)

新发现的 C 层限制，不能忽略：

- pipeline_scaling.py:73 只向提炼器传最后一个 results_i；induce_scaling.py:168–191 的 num_samples 循环又始终读取同一 args.result_dir。沿此静态路径，标为多轨迹的内容会重复读取同一结果；不能把脚本原样运行等同论文机制已经正确实现。
- induce_scaling.py:181–184 把 reward == 0 标为 success；但 :188–191 实际拼接只含 query/steps，没有把该 status 放进提示。因此不能声称“这次发现的相反标签必然污染了当前 prompt”；能确定的是读取/标签语义与论文高层描述需要另行对账。
- :66–85 只取每步 chat_messages 前三项的第三项并跳过异常，不能据此承诺保留全部工具观测。:214 默认 criteria=gt，而不是自评；调用方没有显式覆盖它。这也是不能照默认脚本就声称无 gold 学习的原因。

来源：[冻结提炼器](https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/WebArena/induce_scaling.py#L164)。以上是静态缺陷/限制分析，没有执行脚本，也不据此否定论文所有实验。

#### 3.2 SkillFlow

P：每个任务族从空库开始，按族内顺序运行，轨迹与验收反馈生成增/改/删文件补丁，下一题使用新库；不同任务族重置。该协议刻意排除了跨异质任务的检索混淆，不能作为我们全局混合任务 Skill 检索已解决的证据。[论文 §2.4](https://arxiv.org/html/2604.17308v1)

C：build_group_job_config 明确将 n_concurrent_trials 固定为 1；调度器并行的是不同 group。同题重复并行不是这个当前 runner 的默认行为。[冻结调度器](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/iterative_shared_skills_runner.py#L448)

C：结束回调读取 trajectory.json、result.json、verifier/ctrf.json；取 rewards 的第一个值，以 >=1 判断 passed，生成 patch 后直接 apply。缺少 reward 时 passed 初值仍是 False；这不是我们需要的 unknown 类型协议，也没有逐补丁独立回归门。不能照抄“第一个 reward 就是总效果”规则。[冻结回调](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/iterative_shared_skills_runner.py#L580)

C：patcher 的 prompt 包含精简轨迹、失败测试、异常、reward、终答和当前库；reward 只是材料之一。输出 summary/upsert_files/delete_paths，修订优先、允许空补丁。[冻结 patcher](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/libs/skill_evolution/patcher.py#L296)

P：GPT 5.3 Codex 配置从 52.41% 降至 46.39%；Claude Sonnet 4.6 完成率不变且报告成本增加。Opus 4.6 的完整历史上下文对照为 51.04%，低于 vanilla 的 62.65%。这是“不要把越多轨迹/更多 Skill 当成必然收益”的直接反例。[论文 Table 1、Appendix C.2](https://arxiv.org/html/2604.17308v1)

#### 3.3 为什么额外核对 SkillSmith

前两者不足以解释独立发布准入，因此只追加这一来源。C：主循环先在训练 minibatch 收集失败，再产生候选；启用时检查目标失败上的改善、capability holdout，之后验证平均分回归，再更新 frontier。parent 由 best_state() 选择；验证基线读取已存 parent manifest，未在此分支与每个 child 重新配对采样。[冻结主循环](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/loop.py#L80)

这些 gates 受配置控制，不能宣称永久开启。平均分不退化也不保证每题不退化。_evaluate_state 支持多个 examples 的 concurrency，但没有因此获得“同一 task 多次稳定性”的自动估计。[检查与评测入口](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/loop.py#L164)

O：我们参考其“候选隔离与多层门控”，增加明确槽位、成对采样、未知和成本口径；不需要复制 frontier/生态算法才能实现第一版。

### 4. O：最小并行执行协议

同题第 i 项任务的第 j 次运行：

~~~text
tau[i,j] = Run(task_revision[i], clone(E[i]), S[v], actor_config, budget, random_draw[j])
feedback[i,j] = Evaluate(task_revision[i], final_artifact[i,j], protocol)
group[i] = all planned slots and their terminal records
~~~

必须同时成立：

1. 开始前固定 task revision、环境初态摘要、库快照 S[v]、检索策略与上下文提供清单。同组不要在每次执行前重新读取变化中的 active。
2. 每条运行有独立工作目录、会话、可写环境/外部账号空间；只读 Skill 快照可共享。无法隔离的真实副作用任务不自动做多次并行，标为 non_replayable。
3. repeats=k 是采样数，concurrency=c 是调度上限，c 小于 k 时排队仍是同一采样计划。并行改变延迟，不自动增加独立任务数。
4. 所有槽位完成或明确 terminal 后形成 barrier；没有反馈/超时也保留槽位。只等待“成功的那些”是错误实现。
5. 组内执行完毕才允许形成一次跨轨迹学习输入；禁止 worker 各自直接覆盖共享 Skill 目录。
6. 顺序在线协议中 task i+1 等本轮是否发布确定后再运行。若为了吞吐量把多个 task 并行，明确为 batch-online：同一批固定旧库，批末统一整理/发布；不能冒充逐题在线学习。
7. frozen_eval 可以跨题、跨重复并行，全程禁止学习写回。候选与基线的验证也可并行，但环境和资产隔离。

建议第一版只实现 fixed_repeats 与固定 barrier；保留 repeats=1 的合法路径。k=3 是可选择的工程起始值，不是论文结论或稳定性保证。遇失败才追加执行可以做成另一份诊断计划，不回写覆盖原计划成绩，不采用隐式“直到成功”。

### 5. O：最小数据与配置

不要先增添多个新服务；这些可以是同一 Host 程序中的记录与函数。

~~~json
{
  "execution_plan": {
    "plan_id": "...",
    "purpose": "learning | release | frozen_eval",
    "update_mode": "task_barrier | batch_barrier | none",
    "task_manifest_hash": "...",
    "protocol_id": "...",
    "base_snapshot": "...",
    "repeats_per_task": 3,
    "max_concurrency": 2,
    "stop_rule": "complete_allocated_slots",
    "actor_config_hash": "...",
    "budget_per_run": {},
    "total_budget": {}
  },
  "trial_group": {
    "group_id": "...",
    "task_revision": "...",
    "snapshot_id": "...",
    "context_manifest_hash": "...",
    "environment_snapshot_hash": "...",
    "planned_slot_ids": ["..."],
    "terminal_slot_ids": ["..."]
  },
  "run_slot": {
    "slot_id": "...",
    "run_id": "...",
    "group_id": "...",
    "environment_instance_id": "...",
    "pair_id": "... or null",
    "seed": null,
    "seed_support": "supported | unsupported | unconfirmed",
    "execution_status": "allocated | running | completed | budget_exhausted | infrastructure_error | cancelled",
    "feedback_status": "pending | evaluated | unavailable",
    "artifact_digest": "...",
    "event_stream_ref": "...",
    "usage_refs": ["..."]
  }
}
~~~

种子不受执行器/模型支持时保持 null；固定 seed 不足以承诺模型 API、工具、环境都确定。pair_id 主要绑定相同 task/environment/protocol/budget 的 A/B，不以“随机完全相同”为前提。

每个 Feedback 是有来源的 criterion 结果；任务级 score 是独立聚合产物：

~~~text
CriterionFeedback {
  feedback_id, run_id, goal_revision, criterion_id, evaluated_artifact_digest,
  source_kind: executable | environment | human | llm_proxy,
  evaluator_id, evaluator_version, feedback_permission,
  verdict: pass | fail | unknown,
  score: number | null, score_range: [min,max] | null,
  evidence_refs, reason_code, checked_at, received_at
}
TaskAssessment {
  run_id, protocol_id, criterion_feedback_ids,
  task_verdict, task_score: number | null,
  aggregation_rule_id, unknown_reasons
}
~~~

程序退出 0、Agent 自称完成、某一个局部测试通过都不能自动提升成全任务 pass。必需 criterion 缺失时 task_verdict=unknown，不能用其余分项平均掩盖。LLM 的自报 confidence 也不是已校准的成功概率。

提取器看到的是 TaskSpec + 证据片段 + CriterionFeedback/TaskAssessment + 使用的 Skill 身份。reward 可以控制筛选或比较，但不得用唯一布尔值代替这些输入。unknown 运行仍可贡献已观察到的局部事实，例如确定的命令错误；它不能贡献“成功策略已验证”的结论。

### 6. O：聚合时该保留什么

同一题的比较是局部对照，跨题同类经历才提供迁移覆盖。聚合记录至少包含：

- group_id、每条 unique run_id、轨迹摘要/片段引用、评价来源及逐项结果。
- shared_context：所有运行共同的目标/库/环境；differences：真实观察到的动作或策略差异。
- consistent_patterns、success_failure_contrasts、counterexamples、alternative_explanations。
- observed_run_count、distinct_task_count、distinct_family_count；三者不混写成“证据数量”。
- capture_gaps、feedback_unknowns、deduplication/fingerprint 信息。

同一日志的复制、多个 reviewer 投票不增加执行样本量。多次实际运行若轨迹相同仍可记录其重复性，但不声称增加了策略多样性。不能只保留一次成功的轨迹，把其他失败抹掉；也不能将“一次成功与一次失败的不同动作”直接写成因果定论。更详细的长轨迹提取与归因由对应节点研究报告承担。

### 7. O：reward、稳定性与未知的报告公式

对任务 i，预先分配 k_i 个槽位；s_i 个已确认成功，f_i 个已确认失败，u_i 个仍未知，满足 k_i=s_i+f_i+u_i。这里的 unknown 包括评价不可得；执行异常另有状态字段，不伪造成任务失败。

~~~text
observed_SR[i] = s_i / (s_i + f_i)          # 分母为 0 时为 null
coverage[i]    = (s_i + f_i) / k_i
success_interval[i] = [s_i/k_i, (s_i+u_i)/k_i]
macro_observed_SR = mean_i(observed_SR[i]) # 同时报告有定义的 task 数及 coverage
~~~

success_interval 是“未决槽位可能全错/全对”的识别区间，不是统计置信区间；下界叫确认成功比例，不能偷偷宣称 unknown 等于失败。对 [0,1] 连续任务分数可用已知分数和与未知个数构造同样上下界。

至少分报三类成绩：

1. 单次表现：所有计划重复的均值，按 task 等权聚合，避免被加采样的难题改变权重。
2. 选择后表现：Best-of-k 需要真实 selector、chosen_run_id 和该输出的独立评分；selector 的调用也计成本。
3. any-success@k：k 次中至少有一次通过的 oracle 可达性，仅说明搜索覆盖，不能等同部署时能选对答案。

另可给“k 次全部通过的任务比例”，同时记录 k 和 unknown；这是重复稳定性描述，不是所有未来任务的可靠性概率。只有一次 task 的三条成功不能声称三个独立任务改善。

独立冻结任务上的不确定性估计以 task 为聚类单位，模板/任务族强相关时提升到 family；在线学习的各 task 通过库更新相互依赖，若要做严格不确定性比较，应重复完整任务流/顺序，把流作为独立单位。样本不足时报告原始分子分母，不制造显著性。

### 8. O：三种材料权限与防退化发布

| 材料 | 可用于什么 | 不能声称什么 |
| --- | --- | --- |
| D_learn，已完成任务与允许的反馈 | 提取、诊断、生成候选、目标故障重跑 | 同题救回不等于新任务泛化 |
| D_gate，发布开发/回归集 | 选择候选、测目标迁移、旧能力退化、预算 | 反复筛选的集不再是最终未见测试；若反馈回给 proposer，更属于开发材料 |
| D_final，最终冻结集 | 最后统一报告、冻结 Skill 库评估 | 不允许其结果修改同次报告中的候选或提前停止选择 |

在线模式可使用已授权的历史回归材料或独立开发集合做准入；不能偷看任务流未来样本的答案。基础版本、候选、无记忆组可见反馈权限一致。

发布检查用同一任务集合为基线 b 和候选 c 安排成对重复，保存各 pair 的完整状态和差异。第一版优先重新执行基线；复用旧基线只有 task/environment/model/protocol/budget/时间有效期等均匹配才允许，且标明不是同批新样本。随机化或交错 A/B 顺序，避免服务时段漂移。

~~~text
d_i = mean_j(r_candidate[i,j] - r_base[i,j])  # 仅对协议规定且完整可比的 pair 定义
Delta_target = mean_(i in target)(d_i)
Delta_regression = mean_(i in regression)(d_i)
~~~

必须同时公布 planned/comparable/unresolved pairs，不能丢掉单臂异常后只报漂亮的 d_i。若缺失不对称或超过协议阈值，返回 unknown。可做上下界/敏感性分析；不要默认 missing-at-random。

最小准入规则应是多个门，而不是把成功率、钱、长短任意混成一个 reward：

- 结构/资产/兼容性检查通过。
- 评价覆盖和独立任务数达到预设最低要求。
- 目标行为改善达到预设阈值；若采用区间门则需下界达到阈值，否则 unknown。
- 回归集合整体不劣于容忍范围，关键 criterion 不出现已确认的新违约；逐题救回和退化都保留。
- 执行与维护成本在预算内，证据不完整则不伪造净收益。
- base_snapshot 仍匹配，候选资产完整；否则 N10 保持旧 active。

阈值、置信区间方法、最低样本数都属于可配置且版本化的产品策略；不存在一个跨任务通用的“3 次就稳定”常数。每次容忍微小退化可能长期累积，因此还应对固定稳定锚点保存回归记录；不能只比较相邻版本。任何有限检查只约束已检查范围，不保证所有未来任务绝不退化。

### 9. O：成本、选择偏差与边界场景

~~~text
C_total =
  C_actor_all_runs + C_evaluation + C_extraction + C_diagnosis
  + C_proposals_all_candidates + C_validation + C_selector
  + C_repair_and_operational_retries
~~~

成本按唯一 usage_id 去重；未知费用不是 0。并行组 wall_time 是组启动到最后终结的持续时间，不能代替全部执行时间之和或 token/金额。分别报告每个计划任务、每个执行槽位及确认成功的成本；分母为 0 输出 null。

边界场景：

1. 第 2 个 worker 失败启动：保留 slot；不能只统计成功启动的两个。
2. 工具超时但最终产物可测：执行异常与任务判定可以同时存在，按验收产物判断，不混为一列。
3. 用户修改目标：新 goal revision/计划，不用新要求反罚旧运行；取消单独报告。
4. 运行途中发布新版：原 worker 继续使用 pinned snapshot，不热替换。
5. 基础环境不能复位：不承诺同题独立重跑；只能观察性学习或在获准的克隆环境重跑。
6. 两个候选各自通过：不能直接合并并发布，组合可能冲突，需重新形成候选检查。
7. 多个候选反复命中同一 D_gate：记录选择次数和预算；最佳选择偏差由最终冻结集检验。
8. 相同 run_id/日志被重复导入：幂等去重；不同独立执行同结果则保留执行身份。
9. 模型参数被代理忽略、随机种子不支持：保存实际可确认配置，不能伪称严格固定随机性。
10. 三条轨迹都得到相同错误答案：一致性只能作为观察，验收标准与反例仍必需。
11. 所有失败源于基础设施：可整理运维事实，但不自动改 Skill 的任务策略。
12. 成绩上升、成本暴涨：分开报告并按产品预算门控，不能只展示成功率。

### 10. 给总纲/HTML 的具体修改建议

不要新增十几个顶层节点。保留 N01–N11，将上述 Q-S01–Q-S10 作为可导航的问题账本，并在节点内补：

- N01：环境隔离/重放能力与任务、数据 split 身份。
- N03：ExecutionPlan、TrialGroup、RunSlot；展示 repeats 与 concurrency 的区别、组屏障和在线更新模式。
- N05：criterion feedback → task assessment 的确定性聚合；画出结果分数、详细证据、原因假说三条不同数据线。
- N06/N07：明确支持同题多轨迹输入；分开记录运行数、任务数、任务族数。
- N09：paired comparison、target/regression、unknown coverage、关键约束与预算门；显示 rejected/unknown 回到保持旧版本。
- N11：三个成功指标、未知区间、独立统计单位与完整成本。

HTML 应展示契约和预期执行顺序，不能用可点的按钮暗示产品后端已实现。本报告只提出 source JSON 的变更清单，未改 HTML。

## Files found

- docs/blueprint/project-contract.json — 本轮审查的目标架构唯一来源，v1.0.0。
- docs/blueprint/build.mjs — 通过 node 子命令按节点读取契约，无产品执行。
- .trellis/tasks/09-18-experience-learning-architecture/resume.md — 当前仍为 design-support；产品实现、模型运行在范围外。
- src/core.ts:209 — 原型 evidence 条数验证，不是任务收益判分。
- src/controller.ts:550 — 原型维护风险结构分，不是候选版本回归。
- docs/references/feedback-selfjudge-comparison-20260918.md — 已有 ReasoningBank 反馈数据流与 MaTTS 阅读背景。
- docs/references/skill-evolution-source-notes-20260917.md — 保留的固定源码事实；原过期执行提案见 Git 检查点 db20db8。
- docs/references/skillsmith-code-deep-review-20260918.md — 既有候选检查和平均分回归边界。

## Related specs

- .trellis/spec/backend/architecture-current.md — 当前行为与目标契约必须分开。
- .trellis/spec/backend/contracts-and-storage.md — unknown、可见轨迹、用户事实与来源不能伪造。
- .trellis/spec/backend/validation.md — 同题重试不是独立任务；在线与冻结分报；全部成本入账。
- .trellis/spec/guides/system-boundaries.md — 修改结构化总纲后再生成视图；研究不是自动生效的实现指令。

## Caveats / Not Found

- 没有运行这些上游代码、模型或任务，所有代码结论是所列冻结提交的静态调用链。
- SkillFlow 逐任务 verifier 数据集未在本轮下载或全面审计，不能证明每个任务的判分完整。
- MaTTS 公开 scaling 脚本存在上述静态数据装配问题；报告严格区分论文机制、公开脚本与本项目选择。
- 本报告不替代其他读者对长轨迹、归因、初始 Skill 集合/检索/冲突的完整审查。
- 当前数值阈值、第一批 benchmark、环境隔离后端与用户模型端点兼容性仍需由主会话确定；不在此报告暗中固定。

## Independent review: v1.1.0 执行/评价/发布链

- Date: 2026-09-18。
- Scope: 仅复查当前 source JSON 的 runtime.parallelism/feedback/metrics/split_policy/release_gate、N02/N03/N05/N09/N10/N11 及关联 schemas/edges/questions。
- Snapshot: meta.version=1.1.0；复查后一次读取 SHA-256 为 07cb71e6c4c0028c8a81ffb0780f2a9aaf6fd9876c08abec3d52e414b75d306c。主会话同时修改，以下采用 JSON 字段锚定位；行号仅对应复查瞬间。
- Method: 静态输入输出与边界反例检查；没有重新联网、运行模型、修改总纲/产品或执行 benchmark。以下是本次发现时的阻断项，不代表主会话修订后仍未解决。

### 阻断项与最小修复

| ID | 定位与问题 | 可构造的失败路径 | 最小修复 |
| --- | --- | --- | --- |
| R-S01 | nodes.N02.preconditions/implementation 只允许 active；nodes.N09 需要准确 candidate 的上下文和 RunGroupPlan，但没有明确可用于候选的选择/组计划端口 | 复用 N02 会拒绝尚未发布 candidate；绕过 N02 则需要另写一套未约束的选择规则，破坏同一 selection policy 的对照 | 将“默认解析 active”与纯 select_and_plan(task,snapshot,policy,protocol,mode) 分开。normal 只收 active；N09 的 validation 模式可收明确的候选快照，learning_enabled=false，绝不改 active。补 N09 使用此端口的步骤/数据流 |
| R-S02 | nodes.N05.operator/outputs 为 Feedback[] + TaskAssessment，但 implementation.signature 仍为 evaluate(task,artifact_snapshot,protocol) -> Feedback[]（复查时约 613/648 行） | 照实现签名写代码会丢任务级聚合，并且调用者无法从 artifact 参数保证完整 run 身份。N06/N07/N11 已依赖 TaskAssessment | 统一为 evaluate(task,run,protocol) -> {feedback,assessment,usage}，将聚合规则和不可评价分支写进实际返回契约。N03 的 run_slot 是内层端口，另明确 run_group 返回所有 RunBundle + GroupReceipt，避免拿 slot 签名替代节点签名 |
| R-S03 | nodes.N11.inputs 与 edges 没有 RunGroupPlan，签名却接受 all_slots；目前只能从 RunBundle/GroupReceipt 得到计划痕迹（约 1066/1102 行） | 某整组在创建环境前崩溃，既无 RunBundle 也无 GroupReceipt；reporter 看不到它，分母会悄然缩小 | 运行前将 RunGroupPlan 注册到持久化 ledger，新增 N02→N11 的 RunGroupPlan 输入边；N09 的所有 baseline/candidate 计划同样预注册/传输，reporter 以计划为全集，回执缺失只补 unknown 状态不删组 |
| R-S04 | schemas.Feedback.evaluated_state_digest 强制非空 SHA-256，而 RunBundle.artifact_digest 可为 null；N05 的 artifact_snapshot 签名没有无产物分支 | 分配后取消/启动失败且没有可评价终态时，协议要求 unknown，但不能构造合法 Feedback；容易直接跳过，或拿初态 digest 冒充被测终态 | 允许未评价反馈的 evaluated_state_digest=null；仅 evaluator_status=missing/error 且 outcome=unknown、score=null 时使用，写明确 reason。可评价的反馈仍要求真实 digest。无标准可引用时允许任务级 unavailable assessment 的明示分支，不捏造 criterion 或被测状态 |
| R-S05 | runtime.release_gate 的 target 只要求“至少一题均分提高”，未限制其他 target 退化（复查时约 2422 行） | 扩到多个 target 后，一个题从 0→1，另两个从 1→0，transfer 改善且 regression 不变，仍可通过；目标集合净损失被单题救回掩盖 | 参考门改为 target 每题均分不降且至少一题提高；或者预先声明目标加权均值改善与逐题可容忍损失。不要依赖默认 target=1 回避多题语义；明确硬约束门检查 candidate 的哪些标准 |
| R-S06 | N05 可调用 proxy judge，却没有 UsageRecord 输出/边；runtime.metrics 的 C_total 漏评价与选择器，并把 failed_candidates 与 propose/validate 并列加和 | 学习期 judge 成本丢失；同一失败候选的提案和验证费用可能被阶段与状态重复相加。N11 的“全部成本”无法由现有输入保证 | N05 输出独立 evaluation UsageRecord 并通往 N11；实际启用 selector 时同样入账。C_total 按互斥 stage 对唯一 usage_id 求和；failed_candidate 是同一 ledger 的状态切片，不再作为重复加项；未知成本继续为 null |

### 已覆盖、没有重复列为阻断的事项

- runtime.release_gate 和 semantic_checks 已明确 target/transfer/regression 均须非空、计划 slot 必须完整；不能仅因通用 JSON Schema 未表达所有集合条件就宣称允许空验证通过。
- runtime.metrics 已把取消未评价列为 unknown，同时保留 execution_status，没有直接把取消判成失败；R-S04 指的是这个正确语义尚不能通过记录结构传输。
- 三次重复、参考预算和 observed gate 已明确不是总体显著性或永不退化保证；不要求先做参数寻优才继续实现。
- N10 已有候选/base 内容身份、generation 防 ABA、单写者/CAS 和回退事件语义，本次范围内未发现需要另增发布机制的阻断。
- selection/final 细节不进入提炼器的权限方向已明示；适应性选择的集合不冒称最终未见集。

### 六项修复复核状态

- Recheck date: 2026-09-18；仅复核 R-S01–R-S06，未增加审查范围。
- Snapshot: v1.1.0，SHA-256 f0e1ab324d14e0c8918b1f47a7706e611832ce244074730144eb9b52e0527b34。

| 原项 | 状态 | 核对结果 |
| --- | --- | --- |
| R-S01 | resolved at contract level | N02 明确 resolve_active 与显式快照纯选择分离；validation lane 可接 N09 的 base/candidate pin；N09 明确复用纯选择器且不改变 active |
| R-S02 | resolved at contract level | N05 operator、outputs 和 implementation.signature 已统一返回 Feedback[]、TaskAssessment、UsageRecord[]，输入为 run_bundle |
| R-S03 | resolved at contract level | N03/N09 均要求启动前持久化全部计划；N11 新增 RunGroupPlan 输入及 N02/N09 传输边，整组无回执也列 missing/unknown |
| R-S04 | partially resolved | 无产物的 evaluated_state_digest 已允许 null；evaluator_status=ok 仍强制实际 hash；missing/error 强制 unknown/null。剩余同项分支见下 |
| R-S05 | resolved at contract level | target 已改为每题均分不降低且至少一题提高，不再允许其他 target 退化被单题救回掩盖 |
| R-S06 | resolved at contract level | N05 已输出并传递评价 UsageRecord；N02/N04 的开销亦传递；总成本按唯一 usage_id 和互斥 stage 合计，failed_candidate/purpose 为切片标签 |

R-S04 的唯一剩余矛盾：N05 仍规定“标准缺失→unknown”，但 TaskAssessment.criterion_feedback_ids 必须至少 1 项，Feedback 也必须引用有效 criterion_id。没有任何标准/反馈时不能构造合法任务级 unknown；不能为满足 schema 捏造标准。

最小修复：允许仅 outcome=unknown、score=null、unknown_reasons 非空的 TaskAssessment 使用空 criterion_feedback_ids；pass/fail 继续至少 1 项并关联有效标准。此项属于原 R-S04 中已列出的 unavailable assessment 分支。除此之外，本次没有发现六项修复的剩余阻断；以上 resolved 只说明设计契约已贯通，不表示运行时已经实现或实测。

## 主会话收尾记录

R-S04 的最后分支已修复：没有标准时 TaskAssessment 可为空反馈列表，但只能 unknown/null/非空原因；pass/fail 保持至少一条有效反馈。有效未知示例通过 Draft 2020-12 校验，空标准伪造 pass 的派生例被拒。该证据仅说明文档 schema 行为。
