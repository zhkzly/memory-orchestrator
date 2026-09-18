# HTML 总纲与实现覆盖审查

审查日期：2026-09-18。代码基准：`4a71ccf1b030986dec97bfda5d01d4a8745f1b7e`，总纲 v1.5.0。

**结论：已有可运行的 Python 主干，但不能把 HTML 的 11/11 implemented 理解为全部契约已经完成。** 本次复现 9 个正确性问题，其中 3 个 P1、6 个 P2；另有 1 项终态政策/统计口径缺口，以及尚未接通的设计能力和未获得的效果证据。上轮将整个实施任务勾为完成、全部节点标为 implemented，结论过早。

本轮只做审查。没有修复产品代码、改变总纲/HTML 状态、运行 mutation、调用真实模型或运行 benchmark。这里的报告和探针是审查产物，不替代原目标契约，也不表示问题已经修好。

## 证据范围

- 主会话重新运行既有测试：**126/126 通过**，见 [原始输出](baseline-tests.txt)。这不能覆盖下面的新反例。
- 三名 Agent 交叉检查非自己编写的模块；主会话核对总纲、任务、当前源码与既有取证。
- 核对了此前验收记录的 27 个文件哈希，均与当前实现相符，包括归档后更新的打包数据元信息。
- 新探针只使用临时 Store、本地执行/评分函数和固定 JSON 模型替身；真实模型与网络调用均为 0。缺陷探针以“错误确实发生”为断言，退出码 0 表示复现成功，不是修复验收通过。
- 每项定位、优先级及证据索引见 [manifest.json](manifest.json)。源码行号均对应上述基准。

## 一、逐项审查发现

### F01 · 契约/报告口径：非完成产物如何评分，需要明确

定位：`evaluation.py:180`、`:423`，见 [源码](../../../../../src/memory_orchestrator/evaluation.py)。

在本地 CSV 执行结果中加入 `execution_status="cancelled"` 并保留完整正确 artifact，独立 verifier 返回 pass；当前比较与发布确实允许它进入 active。

**这不足以证明错误发布，撤回初审的 P1 定性。** 总纲 `runtime.metrics` 明确是“取消未评价属于 unknown”，并要求区分 execution_status 与任务 outcome；没有规定全部非 completed 产物一律不能被独立验收。超时后已有正确产物的 benchmark 也可能需要这种评分。

实际缺口是：采样路径对非 completed 跳过评价，比较路径允许继续评价，适用政策没有统一说明；比较报告也未按承诺单列取消/超时等执行终态。应明确两种路径的协议及统计口径，不应简单改成“取消等于失败”或无依据地禁止所有部分产物评价。

证据：[输出](probes/n09_n11_results.json)，键 `noncompleted_candidate_is_published`。原行为证据保留，解释已校准。

### F02 · P1：迟到反馈可绑定到另一条已知运行

定位：`store.py:411`，见 [源码](../../../../../src/memory_orchestrator/store.py)。

同题两次执行后，给 episode0 添加一条 feedback，但 `run_id` 和 `evaluated_state_digest` 来自 episode1。保存成功，`binding_status` 仍为 `bound`。当前检查仅核对项目、subject 和 revision，没有核对已知源 run 与产物。

影响：另一尝试的反馈可进入当前经历的学习材料。导入材料允许来源未知，不意味着可以接受已有信息之间的明确矛盾。

验收缺口：需要同时覆盖错误 run、错误已知产物以及来源确实未知的合法导入，不能以强制补齐所有元数据来修复。

证据：[输出](probes/n01_n05_results.jsonl)，探针 `late_feedback_wrong_known_run_and_state`。

### F03 · P1：已知调用关系和目标切换没有传给模型

定位：`evidence.py:174`、`:266`，`learning.py:329`，见 [证据包](../../../../../src/memory_orchestrator/evidence.py) 与 [消费者](../../../../../src/memory_orchestrator/learning.py)。

两份经历的正文和事件 ID 相同，仅交换两个 result 的 `call_id`：索引配对已经不同，去掉随机 packet_id 后 EvidencePacket 却完全相同。另一组仅改变第二条用户事件的 goal_id，索引从 switches 变为 continues，证据包也完全相同。

影响：索引已知道的工具对应关系、动态目标关系在交接处消失，提取/归因模型无法据此区分两种情况。问题不在模型是否足够聪明，而在这些信息没有进入其输入。

验收缺口：原测试分别验证索引结构和文本引用，没有验证“关系变化必须反映到模型可见材料”。补充结构时仍须计入证据预算，不能靠重新全量注入轨迹解决。

证据：[输出](probes/n04_n08_results.json)，键 `call_metadata_loss`、`goal_metadata_loss`。

### F04 · P1：同题组未闭合即可学习并写入经验

定位：`learning.py:65`、`:228`，见 [源码](../../../../../src/memory_orchestrator/learning.py)。

计划两个并行槽位，第二个回调通过有限等待暂停。第一条 run/episode 落盘后，在采样尚未结束且 GroupReceipt 为 0 时调用 learn：发生 2 次固定回复替身调用，写入 1 条经验。返回 noop 只表示没有生成 Skill，经验池已经改变。

影响：正常调用 sample_tasks 会等待汇合，但公开学习入口没有落实 I15 的组闭合条件。异步调用可以在只看到部分样本时更新经验。

验收缺口：应测试并发读取部分组的调用路径。仅对已知本地组要求相应闭合证据，普通导入经历仍不应被迫伪造 GroupReceipt。探针最终释放等待，所有线程正常收尾。

证据：[输出](probes/open_group_results.json)，during_open_group 为 1 条经验、0 个回执、sampling_finished=false。

### F05 · P2：两个相同有效候选会使整轮停止

定位：`learning.py:417`、`engine.py:19`，以及 `evaluation.py:302`。

candidate_count=2，两份合法提案产生不同 proposal_id、相同 candidate_digest。学习返回 proposed；evolve 随后返回 error/duplicate_candidate，execute/evaluate 调用均为 0。

影响：独立提案没有产生多样性时，本可继续评价的那个候选也被阻断。当前“失败候选不阻塞另一个成功候选”的用例没有覆盖合法重复。

建议在进入比较时区分唯一候选快照和提案尝试，保留每次模型调用及费用，不能简单删除重复尝试的记录。

证据：[输出](probes/n04_n08_results.json)，键 `duplicate_candidate_evolution`；固定 JSON 替身 4 次，真实模型 0 次。

### F06 · P2：超时/取消返回的部分轨迹无法进入学习

定位：`sampling.py:175`、`:220`，见 [源码](../../../../../src/memory_orchestrator/sampling.py)。

回调返回 timeout 和合法的已执行 action。原始 executions 中有该事件，派生 Episode 和 EpisodeIndex 中没有；gap 反而写成“事件没有提供”。

影响：原始数据并未被删除，但当前学习入口无法利用这些已知的部分经历。应保留已提供事件并标记未完成，不能把保留事件等同于任务成功。

证据：[输出](probes/n01_n05_results.jsonl)，探针 `timeout_partial_trace`。

### F07 · P2：冻结初态与报告初态矛盾未被检查

定位：`sampling.py:161`。

计划初态为 hash A，执行函数明确返回另一个合法 hash B 及环境身份，运行仍记为 completed，没有初态矛盾 gap。comparability=False 确实避免了宣称独立性已验证，但不能替代对已有矛盾的核对。

这里要求比较已有元数据，不是要求核心提供 OS 隔离或代替外部函数重置环境。

证据：[输出](probes/n01_n05_results.jsonl)，探针 `reported_initial_state_contradicts_plan`。

### F08 · P2：报告漏读已经落盘的评价结果

定位：`report.py:70`、`:118`，见 [源码](../../../../../src/memory_orchestrator/report.py)。

8 条 EvaluationResult 写入后、ValidationRecord 写入前模拟中断，磁盘已有 6 pass、2 fail。报告只从 validations 取结果，因此输出 8 unknown、recorded_results=0。

计划分母没有丢，缺陷是漏读原始结果。报告应区分“已有结果、整轮尚未验收”和“请求根本没有结果”，发布仍必须等待完整验证。

证据：[输出](probes/n09_n11_results.json)，键 `persisted_results_ignored_without_validation`。

### F09 · P2：报告没有采样质量统计

定位：`report.py:148`、`:169`。

只进行三次采样，反馈为 2 pass、1 fail：sampling_slots=3，但 outcomes 全 0，成功率为 null，没有独立采样质量区块。

采样分母已经保存；缺的是采样质量、purpose/update_mode 等统计。候选比较的逐案例指标已有实现，不应把它们也误报为缺失。

证据：[输出](probes/n09_n11_results.json)，键 `sampling_quality_missing_from_report`。

### F10 · P2：验证次数被标成候选数量

定位：`report.py:179`。

同一个不可变候选比较两次均通过，候选实体只有 1 个，candidate_counts.accepted 却为 2。应明确区分唯一候选、提案尝试和比较次数，不能混用粒度。

证据：[输出](probes/n09_n11_results.json)，键 `validation_attempts_labelled_candidate_count`。

## 二、11 个节点的完成度

“有代码”“局部验收通过”“效果验证完成”是不同判断，不能用一个 implemented 字段替代。以下不要求每个逻辑节点必须有独立类、函数或服务。

| 节点 | 当前可确认的实现 | 尚未闭合的内容 |
| --- | --- | --- |
| N01 输入与事实 | Store 保存/纠正事实、导入经历、保留未知来源，两种输入路径可用 | 任务条件由提供方定义；固定 seed 作为标准初始实验臂未接通。不存在名为 receive 的统一函数本身不是缺陷 |
| N02 召回 | 固定快照、词法检索、依赖闭包、冲突/字符预算、提供清单、关系加权 | 事实主要按项目和预算选择；关系 applicable_context/源版本没有筛选消费者。当前字符预算不能标成精确 token 预算 |
| N03 采样 | 先写计划/输入、有限并行、固定版本、正常汇合、终态记录 | F04/F06/F07；进程级中断后的组回执恢复未实现。实际执行/重置/隔离是提供方责任 |
| N04 索引 | 显式修订、call_id 配对、原文字节引用、缺失标注 | F03；非流式读取，没有文件/共享产物依赖链回找。自动目标绑定提示词及校验器未接入 learn/evolve；未知身份保留 unknown 是合法行为 |
| N05 反馈 | 接收/获取反馈、迟到追加、来源与权限区分、错误转 unknown | F02；TaskAssessment 仅有 schema/存储类别，未接多标准/加权协议聚合；代理判断提示词未接入自动路径 |
| N06 提取归集 | 有界片段/补读/弃权、引用检查、精确结构去重、历史反例保留、来源计数 | F03/F04 的交接影响；未实现描述中的失败签名定向检索，语义提取准确率未测。不能凭没有语义聚类算法就要求新增算法 |
| N07 归因 | 诊断、替代解释、非 Skill 路由、目标/引用检查及有限修复 | check_plan 仅保存/传递，没有执行消费者；另给的 case_set 驱动比较，尚无自动区分性/最小组合检查 |
| N08 候选 | 四类操作、版本/规则/路径/所有者/依赖/资产检查、有限候选 | F05；附属脚本只保存文本和 hash，没有自动编译/执行资产测试。不能把这层检查当成工具功能验证 |
| N09 比较选择 | 冻结计划、普通函数执行/评分、逐案例门、成本/稳定性/迁移门、选择 | F01 的终态政策/报告口径需明确；关系定向组合实验与诊断计划执行尚未接通，具体 case 的语义由提供方承担 |
| N10 发布回退 | 重读记录、精确身份、CAS、幂等、孤儿回执处理、历史回退 | 机制已有局部证据，本轮未复现独立的 CAS/身份绑定错误。F01 不足以否定合法产物的发布；当前兼容性主要是项目/完整快照，不能扩称运行环境兼容已验证 |
| N11 报告 | 比较计划分母、逐案例均值/范围/变化、唯一用量、币种/缺失统计 | F08/F09/F10；any/all-success、模式分栏、整组墙钟时间及完整维护开销覆盖尚未完成 |

## 三、28 条问题逐项核对

| 问题 | 本次结论 |
| --- | --- |
| Q01 动机和演化对象 | 事实/经验/Skill 分离有代码；提取质量、维护质量、未来净收益尚无实验结论 |
| Q02 轨迹来源 | 导入/函数输入可用，native 采集明确暂缓；部分轨迹使用受 F06 影响 |
| Q03 与 Agent loop 的关系 | 普通函数边界及 evolve 组合已接通；跨 Agent 实际接入/迁移未验证 |
| Q04 同题并行 | 有限并行与快照固定已实现；F04 组闭合、F07 已知状态矛盾未闭合；外部隔离仍属提供方 |
| Q05 单例/同题/跨题 | 能组织/计数并把材料供给模型；F04 使部分组可提前学习，未显式构造全部差分/对照计划 |
| Q06 偶然成功 | 比较均值/范围/可选稳定性门存在；F08/F09/F10 及终态、any/all-success 缺口影响完整口径 |
| Q07 反馈从哪里来 | 真实函数和已有反馈可用；F02，且多标准 TaskAssessment 聚合未接通 |
| Q08 reward 与提取 | 标量与原始反馈分开，可用于提取/比较；内核尚未实现完整多标准评分协议 |
| Q09 目标变化 | 显式元数据索引存在，未知可保留；F02/F03，自动缺失边界识别未接入 |
| Q10 长轨迹 | 有界片段与补读已实现；F03/F06，流式索引和依赖证据链回找未实现 |
| Q11 截断/并行/子事件 | 原始记录和索引支持身份关系；F03/F06 使模型输入仍缺信息 |
| Q12 提取输出 | completed/needs_more_evidence/abstained、结构及引用检查已接通；不证明主张语义正确 |
| Q13 归集和反例 | 精确 hash 去重、任务/来源计数、历史边界和有限召回存在；专门的失败签名检索/冲突裁决未接通 |
| Q14 是否生成 Skill | 由模型和 route 判断，已有库进入输入，更新受验证门约束；必要性/可重复性没有独立语义验收 |
| Q15 初始库 | 空库 ADD 可运行；seed 可保存/显式读取，尚无标准采样/演化初始实验臂入口 |
| Q16 按任务选 Skill | 词法匹配、依赖闭包、预算和提供记录已有实现；任务相关事实选择/关系适用范围仅部分覆盖 |
| Q17 提供与使用 | 提供清单、来源声明的消费记录、产物/评价分开；实际因果效果未证明，N11 分层汇总不完整 |
| Q18 修改对象归因 | 诊断和目标检查已接通；F03 损失重要输入，check_plan 尚未执行化 |
| Q19 归因是否成立 | 完整候选对照存在；没有自动执行原因区分/最小消融，不能声称唯一根因成立 |
| Q20 修改形式 | 受限操作及完整资产机制已有实现；F05 影响多候选整合，资产功能不由 hash 证明 |
| Q21 Skill 相互作用 | 依赖/声明冲突/co_used 有生产和消费；measured_effect 有记录/消费分支，无内建测量生产及局部组合消融流程 |
| Q22 库增长与冲突 | 数量/操作/附属资产上限和结构冲突检查存在；语义去重/合并主要依靠提示词，增长与维护收益报告不完整 |
| Q23 版本选择 | active/候选与运行快照分开，CAS 配合已实现；广义环境兼容未验证 |
| Q24 避免退化 | 固定质量/回归/稳定性/成本检查存在；终态处理需明确协议，有限测试仍不保证永不退化 |
| Q25 留出集与泄漏 | 已有反馈权限、冻结来源学习拦截和 criteria 隐藏；真实数据划分、重叠审计与未见评测未完成 |
| Q26 发布/过期/回退 | 机械机制及局部拒绝测试存在；未发现可据 F01 断言的错误发布；终态政策与验收依据需明确 |
| Q27 benchmark 与收益成本 | 数据模型/回调便于以后接入；F08–F10 影响报告，尚无正式 benchmark 或收益结论 |
| Q28 模型调用与修复 | 提取/诊断/提案主路径有 schema、输入白名单、预算和有限修复；目标绑定/代理判分辅助提示词未进入完整自动流程，语义准确率未验证 |

## 四、文档本身的状态问题

1. 11 个节点全部 `implemented`，而 28 个 Q 全部是 `design_retained_implementation_paused`。
2. `runtime.non_claims` 仍写“没有运行模型学习”，与已保存的真实 SDK/学习调用冲突；limitations 仍称提示词待实施。
3. authority 中仍把文档对齐任务写成“当前文档任务”，并在已归档实现任务上保留“未来交付、仍未授权恢复”。架构 PRD 第一行仍称学习运行时未实现。
4. `build.mjs:83–92,210–211` 只检查 implemented 是否附引用及对应路径是否存在；`viewer.template.html:198` 按标签计数。它们不是逐义务验收器，不能发现本报告中的跨节点反例。
5. 旧实施清单已全部打勾，但没有逐 Q 的完成证据账本支撑这些总括标注。

应在后续修订中分别表达“机制实现”“行为验收”“调用方责任/暂缓”“效果验证”。不能通过删除原承诺来消除缺口，也不能把缺少 native 接入或 benchmark 一概当成本轮核心代码错误。

## 五、已有证据能证明什么

- 存储、不可变快照、受限操作、模型预算、引用/版本拒绝、CAS 和普通函数组成的主干真实存在，现有实现可保留。
- scripted teacher + 本地 CSV 回调跑通过 ADD→比较→发布→PATCH→再发布→复用→回退；这证明那些构造路径能运行。
- 已保存的三轮真实学习分别是 NOOP、拒绝无效目标、生成候选后没有改善而拒绝发布。它们不是成功演化或泛化提升证据。
- 未完成：原生客户端接入、CLI/MCP/目录同步、正式 benchmark、未见任务收益和净维护收益。它们是明确后续范围/证据边界。
- 浏览器视觉/交互检查没有完成；本轮未绕过已有浏览器 URL 策略限制。

## 六、建议的修复顺序

1. **先修 F02–F04**：绑定已知 run/产物；把已有结构放入有界模型输入；在已知组的学习入口落实闭合条件。每项先加入对应跨节点反例。F01 另行明确终态评分政策和统计，不把未评价的取消、有效部分产物和任务失败混为一类。
2. **再修 F05–F10**：候选快照去重但保留尝试成本；保留部分轨迹和状态矛盾；报告以原始账本为依据并明确统计粒度。
3. **逐义务处理部分实现项**：对 TaskAssessment、check_plan、measured_effect/组合检查、seed、长轨迹索引及报告指标明确最小交付；沿用现有函数/记录，不预建通用框架。
4. **然后修订 HTML/任务完成标注**：每项关联具体代码与验收；效果未验证单独标识。当前审查不替这些修复提前勾选完成。

## 复现方式

从仓库根目录运行，使用当前 `.venv`。探针只在临时目录构造输入和记录，个别探针通过临时方法替身模拟中断；不修改源码。它们依赖当前测试夹具，属于本次审查的冻结复现材料。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python .trellis/tasks/09-18-experience-learning-architecture/research/implementation-coverage-audit-20260918/probes/n01_n05_probe.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python .trellis/tasks/09-18-experience-learning-architecture/research/implementation-coverage-audit-20260918/probes/n04_n08_probe.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python .trellis/tasks/09-18-experience-learning-architecture/research/implementation-coverage-audit-20260918/probes/open_group_probe.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python .trellis/tasks/09-18-experience-learning-architecture/research/implementation-coverage-audit-20260918/probes/n09_n11_probe.py
```
