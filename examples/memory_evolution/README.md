# Python 记忆演化核心

这是独立的 Python 库。调用方提供任务执行和评价函数，核心负责固定记忆版本、组织采样、提炼经验、生成候选、比较、选择和发布。已有经历可以直接导入；用户／项目事实通过显式输入保存和纠正。

## 运行本地示例

```bash
uv venv .venv  # 首次克隆时创建环境；已有环境可跳过
uv pip install --python .venv/bin/python -e .
.venv/bin/python examples/memory_evolution/demo.py
PYTHONPATH=src .venv/bin/python -m examples.memory_evolution.study
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_memory_*.py' -v
```

`demo.py` 使用临时目录，不修改已有记忆。两轮依次展示：CSV 任务失败 → 从空库新增 Skill → 比较和发布 → 下一次任务使用新版 → 修改同一个 Skill → 再次发布 → 回退到历史版本。

CSV 处理、评分、文件存储和版本切换都实际执行。默认 teacher 是明确标注的脚本替身，用于稳定检查完整交接；示例的通过率不能作为模型学习或泛化收益。输入、评分标准和参数都是构造的教学场景；`references/csv-policy.json` 是本例执行器会读取的声明式设置，不是通用 Agent 工具格式。

## 调用顺序

```python
from memory_orchestrator.store import Store
from memory_orchestrator.context import select_context
from memory_orchestrator.sampling import sample_tasks
from memory_orchestrator.engine import evolve
from memory_orchestrator.learning import learn
from memory_orchestrator.evaluation import compare_candidates
from memory_orchestrator.release import publish, rollback
from memory_orchestrator.report import report
```

1. `Store(root)` 显式指定存储根目录。`initialize_project(project_id, seed=None, source=...)` 建立空库或 `{skills, assets}` 预置基线，并记录来源；初始基线不是演化发布。`remember()` 保存事实，`add_episode()` 导入经历，`add_feedback()` 追加迟到反馈；已知身份必须一致，未知字段可以为空。随经历带来的反馈可通过 `feedback_records` 同包导入。
2. `select_context()` 固定库版本，再按任务选择 Skill 和依赖；提供清单记录实际披露内容。新 Skill 的 `scope.retrieval.require_any/exclude_any` 是机器边界：exclude 先执行，require 至少命中一项，随后才进入原 family/trigger 排名。旧 Skill 没有该字段时保留 legacy 路径。默认读取 active，比较时可显式传入候选快照。字符预算和估算 token 均保留计量方式。
3. `sample_tasks()` 在调用前保存全部计划与输入。支持同题多次和固定快照微批；每次执行、取消、异常和未知都计入分母。回调负责环境重置与硬超时，核心的线程池不提供进程隔离。
4. `learn()` 检查来源资格，逐步索引轨迹、关联缺标目标、检索失败模式，再统一经过角色分层与调用组计划。足够短的处理后视图直接提取；长轨迹按阶段预算生成局部记录与精确短引文，再执行经验提取、语义维护、必要性判断、归因和提案。task-family/cross-family 指导还必须引用任务、完整 action/result、以及由相同 artifact digest 绑定的 output/Feedback；只有任务文字和失败分数时会修复、补读、降为 instance 或弃权。补读与格式修复受同一模型实例的显式预算控制。事实记忆不由 reward 改写。返回的 `candidate_ids` 是 proposal ID，可用 `store.get('candidates', id)` 读取完整候选。
5. `compare_candidates()` 固定案例、协议、候选集合和检查义务，执行旧版／候选对照、附属脚本检查及适用的局部组合对照。`ValidationRecord` 表示是否通过，`SelectionRecord` 表示最终选择。缺材料、缺执行或未知不能冒充检查通过。
6. `evolve()` 遇到被拒的candidate target时不原地重试，而把确切评价执行投影成下一轮adaptation Episode，返回`next_episode_ids`。原 TaskAssessment 可用时会复验并保留 criterion feedback；artifact 与新 Feedback 共享 evaluated-state digest。base/regression/transfer/final/unknown不进入；调用方用新的模型预算显式调用下一轮。
7. `publish()` 核对项目、完整资产、确切候选、验证／选择关系和 base/generation 后切换 active。`rollback()` 只回到同项目的已提交发布历史，并产生新代次。下一次召回使用新的 active；正在执行的任务仍用原快照。

记录保存后可以查询，但不一定可以学习。对于本地采样，`learn()` 会检查计划中的全部槽位、实际终态记录和完成回执；`frozen_microbatch` 还检查调用前冻结的全部成员组。父经历、相关经验和同内容历史经验合并使用同一资格判断。未知外部导入可以保留，不要求伪造本地运行计划；已知本地矛盾不能降为未知以绕过检查。

多个提案可能产生相同快照。比较只执行唯一内容，冻结其全部 proposal ID；每次提案和费用仍保留。发布必须匹配该比较中选定快照的真实提案别名。

完整参数和可运行调用见 [demo.py](demo.py)。采样次数、候选数、准入门槛、模型及证据预算均来自显式配置；本例数值不是库的全局默认。

调用方可直接使用 `evolve()` 串起步骤 4–7，由核心选择并发布通过的候选；无需自己重写演化决策。只需积累候选、暂缺评价材料时使用 `learn()`。

一次`evolve()`始终只消费一个Teacher预算。若返回`status="not_selected"`且`next_episode_ids`非空，调用方可以创建新的`StructuredModel`并再次调用：

```python
first = evolve(...)
if first["next_episode_ids"]:
    second = evolve(store, first["next_episode_ids"], new_model, ...)
```

这不会修改上一轮Validation/Selection，也不会把回归或最终测试轨迹变成训练材料。

## 轨迹学习输入与预算

`learn()` 只有一个轨迹输入流程，不能用 `trajectory_processing=None` 切回旧抽样器。可在学习策略中覆盖 `trajectory_processing`；省略时也使用同一算法的默认参数。

- `plan.max_scan_events` 限制候选选择扫描，`max_segments` 和 `max_groups_per_segment` 限制局部包数量与调用组。先按段的重要性选择，再保留段内源顺序，已知目标/修订冲突不强行合并。
- `plan.packet` 沿用字符、片段、目录和估算token四个上限；`role_max_chars` 分别限定 user/action/note/result/feedback/unknown 的原文片段。任务前缀不会被其粘贴材料中的错误词挤走，普通工具回执与重复正文可以折叠，关键错误/反馈仍保留正文。
- `direct_max_input_tokens` 针对完整提取请求的估算值。直接提取不表示全部原文已读：角色裁剪、目录、缺失与coverage仍明确保留。
- `summary_limits.max_observations` 限制每次局部记录数，`max_quote_chars` 限制每条精确引文的字符数。局部模型只整理当前片段；宿主核对引文、计算字节范围、附上匹配的行动/返回短上下文。叙述与原文分开；助手自述不能仅凭自己引用就标成真实环境结果。

长轨迹模型整理要求 `StructuredModel.limits.token_budget`，包含全局 `max_input_tokens/max_total_input_tokens/max_total_output_tokens`，以及按实际prompt ID配置的 `stages`；每阶段设置 `max_calls/max_input_tokens/max_output_tokens/max_total_input_tokens/max_total_output_tokens`。未配置的阶段不能无限调用。完整system、schema、证据、修复消息均计入预检；`preview()` 与实际发送使用同一renderer，实际发送前再次检查。

可运行的参考配置在 [GDPevo入口的MODEL/LEARNING](../gdpevo_pilot/run.py)。按用户最新要求放宽：局部整理每次输入8000/输出1000，最多4次、累计输入32000/输出4000；提取每次输入16000/输出3000，最多2次、累计输入32000/输出6000。两阶段合计输入64000/输出10000。完整Teacher最多12次、累计输入160000/输出24000，另覆盖目标关联、维护、诊断和提案。这是后续运行的可调参考，不重算或改写已归档的51次SDK实验，也不是通用最优参数。

真实轨迹加反馈的最小完整提取请求初次预检约需6435个估算token，证明最初6000的草案上限过紧；现在按用户授权提高，并继续对完整请求逐次检查单次与累计余额。

计数器可通过 `StructuredModel(..., token_counter=...)` 注入，并声明 `counter_id/count_kind`；默认是完整消息UTF-8 JSON字节数除3向上取整的**估计**，不是tokenizer实测或数学上界。合法provider用量用于结算；缺失/失败保留预留而不填零。实际回报超过上限会阻止继续调用，不能把账本裁小。

预算作用于当前model实例，初始preview不预留后续阶段份额，也不保证摘要后一定有预算继续。调用方应为期望流程安排各阶段/全局配额；余额不足时会保留partial或abstained及失败费用。这里不声称跨进程、跨实验臂或账号级预算控制。磁盘原文按范围读取；来源绑定/验证还会读取额外元数据，`max_scan_events`不是全部I/O硬上限，实际read_stats另外记录。

局部中断不会删除之前完成的合法记录；未处理段和模型弃权分别记录。`report().memory_progress.trajectory_processing` 展示每周期计划覆盖、实际完成分析、摘要数量及段状态；token实测汇总不会加入预算预留。以上机制检查不代表摘要质量、归因正确率或学习收益已测。

## 执行与反馈接口

```python
execute(request, snapshot, public_case) -> {
    "artifact": ...,  # JSON 数据，可为 null
    "events": [...],  # 可选：可观察操作／返回，不包含隐藏推理
    "execution_status": "completed",  # 也可 cancelled/timeout/budget_exhausted/adapter_error
    "usage": ...,
}
evaluate(request, execution, full_case) -> {
    "outcome": "pass",  # pass/fail/unknown
    "score": 1.0,       # unknown 时为 null
    "source": "executable",  # executable/human/llm_proxy
    "evidence": [...],
    "usage": ...,
}
```

私有评价标准不传给 `execute`。若回调回传 request/case/snapshot 身份，核心核对是否一致；原始返回和错误另行保存。标量分数和 `llm_proxy` 标签不会自行变成独立真值，实际评价依据由调用方提供。

`scoring_policy` 在运行前写入有效采样政策或比较协议。采样默认 `completed_only`，只评价正常完成且有 artifact 键的返回；比较默认 `available_artifact`，允许独立评价取消、超时或预算耗尽后留下的产物。可显式选择另一个政策。`adapter_error`、错误身份或缺失产物不会被评分；显式 `artifact: null` 与缺失键不同，null 的任务含义由评价方判断。执行终态与任务 outcome 分别报告，不能把取消直接算失败。

`events` 可保留 `event_id`、`parent_event_id`、`task_revision`、`goal_id`、`call_id` 和已知来源角色。采样器统一映射本地事件与父引用；缺失、重复或循环关系保留在原文并标记派生缺口，不补造。

`EvidencePacket` v2 将已知结构和当前披露的调用/目标/父子关系提供给模型；片段、补读目录和关系全部计入 JSON 字符预算。目录只有元数据，不是已读事实。列表内顺序不证明跨线程因果。已知初态不匹配会写入 `initial_state_binding` 和缺口，而不是伪称没有收到初态。

可选 `consumption_events=[{"skill_id": "...", "event_id": "..."}]` 必须关联已提供 Skill 和实际返回的 tool/environment 事件，才记录共用统计；仅提供 Skill 不算使用。共用统计能辅助选择，不能解释为因果收益。未知隔离和消费情况会明确保留。

用量统一为 `tokens={input_tokens,output_tokens,total_tokens}`、`monetary_cost`、`currency`；未知值为 `null`。报告去重计入执行、评分和学习调用，按币种保留已知小计与缺失数，未完成计划不能声称成本完整。

报告按冻结计划读取原始结果，即使尚无 ValidationRecord，也展示已观察成绩并注明尚未验收；它不因此允许发布。采样使用每次运行关联的 TaskAssessment，多标准时复核冻结准则及各项原始反馈。旧记录只在原反馈唯一且绑定可证时恢复，否则 unknown。唯一快照、proposal 记录/槽位和 validation 尝试分别计数；评分政策、purpose/update_mode、执行终态和 any/all-success 分栏。

采样若在 Feedback→Assessment 或 Assessment→RunBundle 之间中断，报告同样可以读取与冻结槽位唯一绑定的已保存成绩。缺失的 Bundle/回执仍单独列出，不生成替代记录；有竞争评分或矛盾身份则保留 unknown，学习准入仍检查实际组/批次闭合。

## 长轨迹、目标变化与经验维护

原始事件可内嵌在 Episode 中，也可每行一个事件存为 UTF-8 JSONL，通过 `trace.import_trace(store, episode_header, path, limits=...)` 归档。JSONL 每行沿用 Episode 的事件字段，带有 `event_id`、`kind`、`text`，以及已知的角色／调用／父引用。`trace.ensure_trace_index()` 按显式 `max_events/max_bytes/max_event_bytes` 增量建立 SQLite 元数据索引与正文文件，可关闭后重新打开续建；未完成时 `learn()` 返回 `needs_index`，不会先把未索引原文全塞入模型。源 hash、原始 JSONL 字节位置、解码后正文片段位置分别记录。

`execute` 也可以返回 `trace_path`，并在 sampling policy 中声明 `trace_limits`。采样器先保存回调原始返回，再归档原始日志与宿主输入／结果事件；原文件逐行字节保持不变，派生档案的偏移不冒充原文件偏移。无需调用方另建一套演化路径。

没有 goal 标签的用户事件通过 `goal_binding_v1` 处理；显式用户切换、修订、恢复或歧义形成旁注，不改写原始事件。窗口内用户内容、已有目标及有限补读计入预算，未知会保留。调用方须在 learning policy 中声明 `goal_binding` 预算；已标注的轨迹不需要再调用这个模型。`resources=[{kind,ref,access,version_ref}]` 可以声明文件／产物读写；有界回找保留父事件、同资源候选及缺口，不把相关性说成确定因果。

提取结果保留适用条件、观察事实、建议步骤、正反证据和未知项。失败签名参与后续检索；`maintain_experience_v1` 的 `LINK_DUPLICATE/MARK_CONFLICT/REVOKE/NOOP` 是可追溯的派生关系，后续检索确实消费，原始经验不删除。未解决冲突会一起暴露，不能靠相似合并隐藏反例。

诊断同时比较本次提供的已有能力与预期行为差异。没有新增行为则 NOOP；证据不足则 needs_evidence；允许 ADD 才能生成新 Skill。PATCH/RETIRE 操作受确切 revision、规则 ID、证据和包大小限制。判断是否重复或该生成 Skill 仍是模型假设，后面的实际检查决定候选能否发布。

## 多标准反馈与代理评价

在采样 policy 或比较 protocol 中传入 `feedback`：

```python
feedback = {
    "criteria": [
        {"criterion_id": "identifiers", "rule": {"expected": "001"}, "weight": 1},
        {"criterion_id": "total", "rule": {"expected": 3}, "weight": 3},
    ],
    "aggregation": {"kind": "weighted_sum", "threshold": 0.75},
}
```

宿主在执行前冻结 FeedbackPlan，每个准则有独立 request ID。`evaluate` 收到该项的 `request.criterion_id` 与 `full_case.criteria`。加权反馈缺一项仍保留原分母，score 为 null 并报告上下界；`binary_all` 任一已知必需项失败即总体失败，缺项覆盖率仍保留。默认兼容单 `task_outcome`。

没有外部评价时，可在采样／`assess()` 中显式配置 `feedback.proxy={enabled:True, limits:模型预算, packet_limits:证据预算}` 并传入 `proxy_model`，实际调用 `proxy_judge_v1`。原始证据、准则判定、费用、失败和修复都入账；来源始终是 `llm_proxy`。比较的 `allowed_sources` 独立决定这种来源是否可用于发布，默认示例只允许可执行检查。代理分数不能冒充外部验收或独立真值。

## 检查义务、脚本与局部关系

`evolve(..., verification=..., execute_view=..., asset_runner=...)` 和直接 `compare_candidates()` 走同一验证路径。`verification_catalog()` 只将公开检查说明和可信 `check_ref` 给模型；标准答案留给 evaluator。诊断和提案的 `check_plan` 取并集，同内容候选的全部提案别名也取并集。不存在的引用需修复，明确为 null 的必需材料会阻止发布。

`verification` 可提供 `checks/cases/asset_tests/relation_pairs/relation_policy`。追加案例会增加真实请求；原来的 `quality_case_refs` 单独固定，额外检查不能用高分稀释原质量集上的退化。默认 `verification=None` 仍验证原 case set 中的义务，绝非关闭验证。

候选中有 `scripts/` 资产时，默认实际执行 Python 编译和可信功能 fixture。fixture 指定入口、参数、stdin、输入文件、预期输出／文件、超时、输出上限与隔离要求。缺功能材料、语法错误、错误结果、超时均不能通过。默认实现有临时目录、环境白名单和进程清理；它提供进程隔离，不提供操作系统沙箱。要求 sandbox 却没有对应运行器时返回 unknown。完整材料结构与真实运行例见 [脚本及组合检查](../../tests/test_memory_verification.py)。

局部关系检查用真实 `execute_view(request, view, public_case)` 比较两个保留依赖闭包的视图。view 有独立 hash，包含实际提供的 `skills/assets`；不能拿完整 snapshot 执行后只换标签声称移除了 Skill。两个合法视图相同时记录 `not_identifiable`，不会编造增量 0。完成结果可产生条件增量 `measured_effect`；后续选择核对源版本、依赖、背景与任务范围后才使用。共用统计 `co_used` 与测得效果分开。

## 中断恢复与报告

```python
from memory_orchestrator.sampling import prepare_sampling, resume_sampling
from memory_orchestrator.evaluation import resume_comparison

prepared = prepare_sampling(store, tasks, policy=sampling_policy, context_policy=context_policy)
sampled = resume_sampling(store, prepared["batch_id"], execute, evaluate)
# 已有比较从原 comparison_id 继续，不另建一份计划：
# resume_comparison(store, comparison_id, execute, evaluate, execute_view=execute_view)
```

原始回调返回先持久化，随后产生评分、运行记录和完成回执。返回已经保存时，从原记录重建后续阶段，固定 IDs 避免重复计费。只有 started 没有 return 的调用会 blocked；必须按 request_ref 提供有来源／证据的 `attach_result`、`confirmed_not_executed` 或 `close_unknown` 处置，不能自动重跑可能已有副作用的调用。比较、组合与脚本检查复用该协议。本地锁防止并发恢复同一计划，不声称分布式 exactly-once。

`report()` 读取真实持久记录，包含：

- 各计划的固定分母、未知、准则覆盖、旧／新差异、回归、any/all-success、执行终态。
- 每次物理调用及失败尝试的 token、费用、币种和价格版本；transport 提供的明确价格保留，未知价格不估算。started 无 return 的尝试不能因后来重试成功就变成零成本；未终结的学习周期同样阻止完整费用声明。
- 本地准备、选择、索引、提炼、诊断、提案、验证、发布、恢复、报告的维护计时；扣除另计的调用等待。批次活跃墙钟时间单列，不拿各并行调用时长之和冒充用户等待时间。
- 版本增长、规则数、资产字节、新增／移除 Skill、维护动作、冲突、失败签名命中、轨迹索引／正文读取和必要性决策。
- 提供、执行器报告的读取／行为、局部效果四层证据；没有级别的消费事件只记 unclassified，不推断为真实使用。

报告自身计时在返回时完成，由 `report_measurement_ref` 引用；该报告里的汇总仅覆盖此前完成的计量。未定价的本地维护成本与已知调用费用分别呈现，不能宣称全成本收益。

## 三种实验模式

`experiments.run_experiment(root, dataset, execution_factory, model_factory, ...)` 直接复用上述核心。`dataset` 提供 adaptation 任务、selection case set 和 final 任务；三臂分别为 online、frozen、frozen_microbatch，使用独立 Store、相同空库／seed 和每臂相同预算。每步先持久化本题成绩再允许学习；最终集固定记忆且禁止反馈回流。

声明 `unseen_scope='instance'` 或 `'family'` 时，必须提供 source_id/task_family，并审计最终集与适应／选择集的身份、源、内容和任务族重叠。未见范围只针对本次记录的材料，不推断模型预训练时没见过。脚本、代理教师或调用方提供的 benchmark 可以用同一入口；数据与 evaluator 的真实性仍由实验者负责。

完整三臂用例见 [study.py](study.py)，`run_study(root)` 可保留全套记录；对应的实际行为检查见 [实验消费者](../../tests/test_memory_experiments.py)。实验 ID 不可覆盖；部分运行保留原计划、原任务成绩和 blocked 状态，原采样／比较可按其 ID 恢复，不能静默重跑整次实验。这里的 Python API 不依赖 CLI/MCP 或客户端目录同步。

## 接入实际模型

```python
from memory_orchestrator.model import StructuredModel, make_openai_call

model = StructuredModel(
    make_openai_call(model="gpt-5.6-terra", base_url="http://localhost:8317/v1", timeout=30),
    limits={
        "max_input_chars": 100000, "max_output_chars": 16000,
        "max_output_tokens": 4000, "max_total_input_chars": 500000,
        "max_calls": 12, "max_format_repairs": 1,
    },
)
# OPENAI_API_KEY 由环境提供；不要把密钥写入任务或存储。
# learn(store, episode_ids, model, policy=explicit_learning_policy)
```

处理长轨迹时，还需在上述 `limits` 中配置前文的 `token_budget` 与各阶段配额；完整参考见 [MODEL配置](../gdpevo_pilot/run.py)。这段最小配置用于可以直接容纳的短输入，缺少长轨迹预算时会正常弃权。

模型模板与 Schema 从总纲精确打包；SDK 不进行隐式重试，格式和纯引用／目标语义修复共用显式额度。原始输出、失败、实际 token 与未知费用保留在账本。测试替身、真实 SDK 接线、真实学习调用及 benchmark 效果是四种不同证据。

代码当前实现的是本地文件版本和函数边界。CLI、MCP、原生会话自动采集、Codex／Claude 适配与 Skill 目录同步仍属后续范围；旧 TS 保留。
