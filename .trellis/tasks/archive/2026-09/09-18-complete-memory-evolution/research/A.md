# A：反馈、初始化和恢复实际实现

所有权：store.py / sampling.py / lineage.py / feedback.py / tests/test_memory_store.py / test_memory_sampling.py / test_memory_feedback.py。未改用户数据、原生Agent接口、总纲、模型源码或其他代理文件；没有真实模型/网络/benchmark/提交。

## 逐义务消费者对账

| 义务 | 实际入口与下游 | 区分性验收 |
| --- | --- | --- |
| O03 | freeze_feedback_plan→assess→Feedback/TaskAssessment→verify_assessment；C发布和root报告复用同一重算 | `test_multiple_criteria_are_called_separately_and_weighted_from_original_feedback`、FeedbackTests二值/加权缺项、proxy真实StructuredModel修复与来源降级拒绝；C独立A复核含混合来源拒发布 |
| O10 | initialize_project→baseline_ref→ensure_project/sample_tasks→release_history/CAS | Store seed第0代/替换拒绝、sampling seed真实消费；C-review-A.py实际seed与legacy空库都经CSV比较发布并重开 |
| O11 | prepare_sampling→CallbackAttempt/Return→resume_sampling→真实Group/BatchReceipt；共享recovery_lock供C | 六个派生保存点中断恢复；真实os._exit；execute和evaluator各自失联；并发恢复；快路径缺RunBundle仍拒绝；confirmed_not_executed/attach_result/close_unknown都留原尝试 |
| O12 | callback原usage稳定ID、local stage_measurements、sampling_segments/batch receipt→root报告 | 恢复不双计tokens；输入预算0调用不造usage；hard-exit批墙钟缺段不补0；B/C复核保留实际读量/请求数，完整成本有缺测仍unknown |

## 当前执行证据

- RED：Store seed/applicability 接口缺失；2 个真实消费者测试分别 AttributeError / TypeError。
- RED：sampling 无 prepare/resume，且多标准 evaluate 没收到 criterion_id；3 个消费者失败。
- RED：Feedback 模块不存在，binary/weighted/重复标准 3 个用例失败。
- RED：已保存计划但尚无 execution 的 final run 可被当 unknown 导入学习。现在 lineage 将真实 slot 也识别为已知本地源，拒绝学习；未造 RunGroup。
- GREEN：A三个测试模块已有67个不同测试；最后一轮费用test显式加三个模块共执行68次（费用test重复一次），exit 0 / 5.7秒。命令：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest tests.test_memory_sampling.SamplingTests.test_proxy_costs_follow_transport_usage_in_success_failure_and_missing_cases tests.test_memory_store tests.test_memory_sampling tests.test_memory_feedback -q`。
- 实际本地子进程 `os._exit(19)` 留下 started 无 return；重新打开 Store 后不会重跑，明确 close_unknown 后批回执仍记录 1 个缺测墙钟段。
- 六处中断验收：execution 原文、Feedback、Assessment、RunBundle、GroupReceipt、BatchReceipt 写入后中断，恢复后 execute/evaluate 各一次，完整产物各一份、usage 两份，不重复调用。
- 代理评价经 StructuredModel 实际序列化/本地 schema / 纯引用检查 / 显式调用预算，用构造 SDK 响应完成；计量保留 input_tokens=11，并拒绝将 llm_proxy 改为 external。这不是实际模型语义准确率证据。
- 代理引用修复在原2次预算内完成，两个调用均计费；输入预算在调用前耗尽则0个provider调用和0个伪造usage，诊断仍保存。
- 两个并发恢复者只产生一次实际执行和一个批次回执；迟到人工纠正追加新assessment并显式supersedes，不能覆盖原RunBundle的权威评估或偷换rubric。
- 已知comparison/contrast的真实request或原execute返回被重新导入时仍禁学；只有未识别的外部来源保留unknown导入路径。

## 数据流和交接

1. `prepare_sampling` 保存输入、稳定run/episode/feedback plan/assessment身份、库与政策，全部完成后才允许执行。
2. `call_recorded` 先写 CallbackAttempt，实际函数返回后先写 CallbackReturn，再派生执行原文/经历/评分。已有 Return 复用；只有 started 无 return 时阻断。恢复凭据以新 RecoveryResolution 追加。
3. `freeze_feedback_plan` 固定标准/权重/阈值/评分资格及请求身份。`assess` 逐标准调用 evaluate 或显式proxy；反馈保留原return、artifact、revision、来源和权限。
4. `aggregate` 原文规则：可信必需fail使binary为0但不抹缺项；全pass为1；其余unknown。weighted缺项不缩分母，保留bounds和来源集合。
5. `verify_assessment` 读取计划和逐项原反馈/return重新核对身份并聚合，供 Store/报告/发布复用；不要求组闭合。旧单项评估保留严格兼容读取。
6. seed初始化是第0代baseline，snapshot项目重绑定但seed内容hash不随project改变；active/release_history/CAS保留baseline根，不能原地换seed。
7. 完成恢复快路径重新检查所有实际槽位、RunBundle、Episode和回执。物理闭合共用 `lineage.verify_group_completion`；学习另外检查purpose和微批完整性。
8. 回调用量主键固定为 `attempt_id:usage:index`，不重复计量；原文统一字段raw。没有返回的attempt没有伪造usage，报告需另外列出未知调用成本。local阶段按真实prepare/select/执行结果整理/evaluate/recover计时，外部等待不算本地维护时长。

返回：prepare为`{batch_id,plan_ids,planned_run_ids,run_ids:[],episodes:[],receipt_ids:[],blocked:[],status:'prepared'}`；sample/resume另有`batch_receipt_id`，run_ids只含真实RunBundle，blocked保留request_ref/attempt_ref/stage。

## 实施调整与边界

- Root确认二值规则后按canonical纠正调查稿；不因缺项把已知必需失败改回unknown。
- 第一次代理测试用了错误的测试预算字段max_fragments；检查实际EvidencePacket消费者后改为已有max_catalog_refs/token_budget，未弱化产品校验。
- 不复制新的callback原文到旧evaluation_returns。新主链由assessment/feedback→callback_returns消费；C负责迁移旧原文数量断言，避免无消费者镜像。
- 旧无started协议记录：已有完整运行可复用；已有唯一原执行与评估可补RunBundle；不确定旧评价是否已发生时明确blocked，不将“没找到记录”解释为未执行。
- attach_result、confirmed_not_executed、close_unknown是调用方提供的显式恢复证据；实现检查身份和记录完整性，不声称能验证远端进程或消除未知副作用。
- 官方mutation已完成18/18，全部exit 0且每项目标before/after SHA-256相同；命令在A-mutation-commands.json，逐项原始输出/退出/恢复hash在A-mutation-results.json。覆盖seed/fact、binary/weighted/重复标准、原artifact/proxy来源、未知执行重试、用量去重、完成清单、计划/比较/callback/流式父链用途隔离、proxy有限索引、外部未知父保留和transport费用。没有变体存活，没有放松断言或现场修改产品。最终全套/提交由root统一执行。

## 已闭合的流式交接

- execute可返回trace_path（本地JSONL）与调用前显式policy.trace_limits；系统先保存CallbackReturn，随后流式复制原行，并加入可追溯host instruction/result，调用B.import_trace冻结单一事件源。原文件不改；offset仅描述复合档案，不冒充原文件偏移。
- request携带固定episode_id；trace_ref直接引用只接受该slot已有的精确header。采样不把内存事件与trace_ref同时送进索引。
- proxy通过B.index_episodes(store,trace_limits)推进；needs_index→blocked(stage=proxy_index)，后续resume继续，未完成索引前0模型调用。真实测试最终只1次execute、1次proxy，events=[]而证据从档案按范围加载。
- lineage读取完整checkpoint.parent_episode_refs：已知final父拒绝学习，未知父不伪造，missing_parent_episode_refs显式返回；raw callback ID也能通过实际attempt.run_id关联已知源，已知无run的本地比较callback不会被当未知外部数据。

## 对 C 的独立有界复核

A在C代码稳定时只读仓库、使用独立/tmp Store执行真实本地CSV回调。脚本和原始结果已保存为 `C-independent-review.py` / `C-independent-review.json`；后者包含源码hash和全部请求ID。重跑：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python .trellis/tasks/09-18-complete-memory-evolution/research/C-independent-review.py /tmp/memory-c-review-new-root`（使用新的目录）。

- 相同base/candidate/material hash，只有diagnosis.check_ref从left改为right：实际请求分别是identifiers/sum/optional-left与identifiers/sum/optional-right，各12次，unused始终不跑，原target/regression保留。
- 已accepted但未发布时，改asset raw stdout仍保留pass标签：N10拒绝asset_binding；换成未验证candidate：拒绝selection_mismatch；改变contrast.value但不改变原成绩：拒绝contrast_result。
- 三个反例均未推进active；保留原证据的正常控制组均可publish。没有发现root指定O06/O08边界中的实际偏差；不是全面证明所有C机制或模型语义。

## 对 B 的独立有界复核

脚本/结果保存为 `A-review-B.py` / `A-review-B.json`。重跑：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python .trellis/tasks/09-18-complete-memory-evolution/research/A-review-B.py /tmp/memory-b-review-new-root`。所有写入为独立/tmp Store，未改B源码、未mutation。

- 12条磁盘事件含缺标用户目标A→B→A：前两次learn返回needs_index，模型0调用；完成索引后3次goal_binding和1次extract。提取输入真实包含derived resumes，原观察goal字段仍null，原JSONL和Episode header不改，并禁止整文件read_text。
- 将final父藏在磁盘子事件里，依赖读取预算即使为0，实际learn仍报learning_not_permitted，模型0调用、经验0写入。
- 真实learn产生维护LINK_DUPLICATE后，下一次真实extract输入只含一个代表；两个member IDs和历史反例标记均保留，原经验不可变。
- 本轮指定范围未见消费者偏差。记录了375次range reads/21184行metadata读取，属于该构造数据和预算下的开销观察；不从“流式/有界”推导速度或净收益。

## A/B 后续同族来源收口

- B发现inline外部未知父与trace未知父不一致；N01/N04没有拒绝不完整外部父引用的要求。新增Store红测真实NOT_FOUND后，统一为原ref保留、不造父对象、missing_parent_episode_refs明确返回；已知跨项目及同Episode不存在的parent_event仍拒绝。
- 已归档parent的events=[]不能被误解释成其事件不存在；已知元数据先校验，事件正文关联仍由索引/证据缺口表达。
- B随后用全部公共入口复现三层反例：inline child→尚未索引的trace parent→known final祖先，正文依赖预算0时原本可以extract。A将整个父链unindexed_trace_refs回传，B在实际learn用显式trace_index推进并重审；历史经验在来源索引未完成时不得参与召回。该修复针对实际禁学边，不添加通用调度器。

## O12 模型费用窄修复

根代理确认transport费用字段在model entry中的交接后，A代理评价消费者也复制monetary_cost/currency/price_version并走既有normalizer。红测真实暴露成功和格式失败两种调用费用丢为null；修复后真实StructuredModel→assess→CallbackReturn→usage三场景全绿。明确提供的0.125/test-unit/transport-price-v1保留；未提供时null，模型生成正文声称“999 CNY”不作为用量；格式失败的调用仍计实际transport费用。未发真实模型请求，数字是构造provider envelope，不能当API价格测量。
