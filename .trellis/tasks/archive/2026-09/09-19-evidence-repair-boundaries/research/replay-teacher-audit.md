# 有界回放 Teacher 与候选独立审查

本审查仅读取 `research/pilot/revised` 已完成 Teacher 输入/返回、指定 Store 记录及相关 `calls-replay` 请求。没有启动测试、模型、网络或 benchmark，没有读取 test001/gold，没有修改产品、提示词、参数或评分器。整体执行次数、分数、成本由根代理汇总。

**新 reason 视图已经进入实际引用链，并支持模型走到经验、归因与候选。产物是一个明确限制范围的 Northwind 逐字段核对流程，尚不是经过效果证明的业务修复。** 前三个局部摘要保留并进入提取；第四个失败没有抹掉已有有效结果。审查完成时比较结果尚未落盘，本文不宣称选中或发布。

## 1. 新反馈是否只是摆在输入里

不是。可直接追踪的链如下：

| 层 | 实际证据 |
| --- | --- |
| 局部正文 | [01 输入](pilot/revised/teacher-inputs/01-summarize_trace_v1.json) 含 `ev:b1564b8f87528965274ffc77:0:950`，`raw_ref=feedback:…:task_outcome#/reason`。它与完整 Feedback 引用是不同原文视图。 |
| LLM 摘要 | 01 的 outcome 引用了 reason 中 `SP002…matched:false` 和 `SP005…matched:false`；[03](pilot/revised/teacher-inputs/03-summarize_trace_v1.json) 又引用订单集合、库存、客户例外等评分项。不是宿主替模型填写这些观察。 |
| 宿主交接 | [05 extract 输入](pilot/revised/teacher-inputs/05-extract_v1.json) 同时保留三份 `trajectory_summaries`、模型报告身份与精确短原文。例如 reason `340:401` 是库存项，`670:714` 是最终决策项，`568:616` 是客户例外项。 |
| 经验 | 05 输出的 observed_facts/supporting_refs 使用上述 reason 短范围，区分 matched 与 unmatched；完整反馈外层 `outcome=fail` 仍走其旧引用。 |
| 归因／候选 | [06 diagnose](pilot/revised/teacher-inputs/06-diagnose_v1.json) 和 [07 propose](pilot/revised/teacher-inputs/07-propose_v1.json) 继续使用同源引用，提出需单独评价的流程假设与 ADD 候选。 |

独立机械核对得到：

- 前三份已接受摘要的 **19/19** 条 quote 都是各自已提供 fragment 的精确子串，且不超过 240 字符。
- 上层三个 summary 的全部 quote_refs 都能在 05 的原文 fragments 中找到；reason 短范围的 UTF-8 字节切片和 raw_hash 与原 reason 视图一致。
- [真实 SDK 摘要请求](pilot/calls-replay/call_0001.start.json) 和 [真实 SDK 提取请求](pilot/calls-replay/call_0005.start.json) 都包含对应 ObservedTeacher 保存的完整 packet，不是只在旁路日志中存在。

这些核对证明数据流、身份和原文对应关系，不证明自然语言观察的每个语义判断都正确，更不证明流程建议能提高业务成绩。

## 2. LLM 实际写出了什么

### 三份被接受的局部整理

1. 01：任务要求、读取 answer_template 的动作、局部官方评分反馈。
2. [02](pilot/revised/teacher-inputs/02-summarize_trace_v1.json)：读取 expedite_queue_memo 的动作与其成功返回前段；列举可见订单开头，明确列表截断。
3. 03：最终 artifact 的局部内容（如 SO-70000 被输出为 shortage/backorder），以及整体失败与可见评分项。

摘要均保留缺口：没有完整模板、完整 memo、ERP 查询链或全部 artifact；没有把不可见的分析补造为 intention。三个局部窗口来自**同一个失败经历**，不是三个独立任务样本。

### 一条经验

[保存的经验](pilot/revised/store/records/experiences/7e1a91efe93377bde20eb3f1ba88c85fd1fb598a81f54e438c5d2ec22332c2fd.json) 的 kind 为 `pitfall`：不要把部分正确的 ERP 输出当成其余分类也正确；建议建立每订单的证据工作表，分别核对库存/短缺、SKU 例外、客户、决策、下一步动作和运输报价，再检查模板与格式。

保存内容与 05 的 experience draft 相同。宿主记录 `status=unverified_experience`，`source_episode_count=1`、`known_task_count=1`、`known_support_task_count=1`。模型自身明确写出：该建议来自一次失败，精确错误来源未知，并不构成跨任务提升。

值得保留的能力边界是：05 的 `missing_evidence` 指出仍需完整模板、memo、ERP 查询及最终 JSON，**但 `read_requests=[]`**。模型选择在现有片段上形成有限 pitfall，没有进一步请求补读。因此本轮不能声称“从轨迹中找到了具体库存公式或某个 API 调用的错误”。这不是宿主替模型作出的业务结论。

### 一项归因与一个 Skill 候选

[保存的归因](pilot/revised/store/records/diagnoses/1bae10b9dbadb7af9aa72fa5f6da8b903b27a72f0c4382e323b575f8a190bad7.json) 标记 `decision_origin=model_proxy`；其 draft 与 06 输出相同。route 为 skill_patch，假设是“将各类字段的证据收集与检查分开，可能减少不匹配”；同时保留规则误解、记录检索不全/过期、序列化问题等替代解释。空库下没有可 PATCH 的已有 Skill，模型提出 allow_add=true。

`necessity.repeatable=true` 是模型对潜在复用性的判断，**不是已经完成重复实验的统计结果**。同一 draft 的 unknowns 已说明重复效用未建立。

[保存的候选](pilot/revised/store/records/candidates/dd3dc313e88a03fea317494dc4acb4a6dd098e7669c314c89addbdf813fecb33.json) 为：

- `proposal_id=proposal_2e08285fa51c42fab10aab82c7627f4e`；候选 digest `de057a6066291b03928eec39d63111b41f52519b5d565e6be8b58c34775f3b5d`。
- 一次 ADD，标题 **Verify Northwind Dispatch-Control Fields Independently**，无 asset_edits。
- 七步流程：读 memo/模板 → 按订单检索所需记录 → 分类建立证据工作表 → 根据实际材料分别推导字段 → 填充模板 → 一致性/排序/货币检查 → 返回 JSON。
- task_family 为 northwind_erp，但范围条款限制 dispatch-control 工作流；排除把这一套字段或动作词汇强加到不同 allocation/transfer 任务。
- 目标检查保留 `case:train_001`，回归检查保留 `case:train_004`；没有取消回归或声称私有预期答案已提供。

它比一句“认真检查答案”更具体：列出了业务对象、字段类别和操作顺序。但它仍是**流程清单式改进假设**，没有提供库存可用量公式、实体 join key、订单级错误定位或新工具。评分组的失败不能证明先前 Agent 真的采用了“某些字段正确，因此其余字段也正确”这一心理捷径；这条建议应当靠后续执行效果评价，而非用标题或 quote 合法性认证因果。

## 3. 机械职责与语义职责是否混在一起

当前已完成产物中没有发现宿主替 LLM 硬编码 Northwind 业务规则的证据：

- reason 提供方式改变了可引用的原文表示；具体摘要、经验、归因和七步 Skill 文本来自 Teacher 返回。
- 保存的 experience draft、diagnosis draft、candidate patch 分别等于 05、06、07 的模型产物。
- 宿主提供了身份/hash/短范围、预算、允许操作、候选快照和检查目录；没有把“评分项未匹配”机械改写成某个正确业务答案。
- 经验状态仍为 unverified，归因来源仍为 model_proxy，候选仍携带目标/回归义务。候选进入库的物理保存不等于 active 已发布。

这只是对本轮数据流与产物的审查，不是对模型所有语义断言的自动认证。scope/exclusions 也是候选中的行为指令，不能当成已验证的跨任务适用性。

## 4. 第四段失败与上层继续

[04](pilot/revised/teacher-inputs/04-summarize_trace_v1.json) 的一次 quote 长 299 字符，超过明确的 max_quote_chars=240；[错误记录](pilot/revised/store/records/errors/11332077119d64f46d9bb9d3067dafba14c8c621c099b7324173311b7f65cecf.json) 保留 `summary_evidence` 诊断。修复尝试预检因 summarize 阶段 `consumed=4, requested=1, limit=4` 被拒绝，最终错误码为 model_budget_exhausted。

不能把它写成“新 reason 表示又出现同样的转义错误”，也不能写成全 Teacher 累计额度耗尽。这里是单引文长度检查和该阶段调用次数限制。前三段的合法结果实际进入 05，证明本轮未因第四段失败而丢弃它们。本文不额外汇总 SDK 费用。

## 5. 比较与发布边界

截至本次审查，`revised/result.json` 尚未出现，比较仍由根代理监控。本文只确认：已经产生并保存候选，目标/回归检查义务仍在；**是否通过、选中、发布，以及实际收益均未由本审查确认**。

最终若得到对照结果，仍需分别陈述逐题结果、重复次数、未知/失败和发布决定；同一失败经历上的三次有效整理、19 条正确 quote、一条经验和一个候选，都不能替代这些效果证据。test001/gold 不在本审查材料中。

## 6. 最终发布边界补核

比较结束后读取 [result.json](pilot/revised/result.json)，并按冻结 plan 的 request_id/case_ref/arm 对齐实际结果。每题每臂仅一次：

| 开发任务 | Base | Candidate |
| --- | ---: | ---: |
| train001（target） | 5/17 | 5/17 |
| train004（regression） | 12/17（记录 0.705882） | 10/17（记录 0.588235） |

[ValidationRecord](pilot/revised/store/records/validations/c380790dbc6140fd92617ecaf3f000aee83945471abf0ca29e1d7f45fc882682.json) 为 rejected：complete_results 通过，但 target_gain、regression_non_decrease 与 verification_complete 未通过。[VerificationRecord](pilot/revised/store/records/verification_records/794fc34b5fc46b7bfb348e54c040ab07ac37e1056d74080700ec94ad391d3256.json) 的 status 为 fail，四项 requirements 均 fail、各自有结果引用且 gaps=[]；这是**实际检查结果未通过，不是缺材料或未执行**。

[SelectionRecord](pilot/revised/store/records/selections/8b5cc8ea80f139d537c16f2b4cd647d9e05d11d912d93810ce1e02461bb4d1df.json) 决定 keep_current，未选 candidate 或 validation；最终 evolution.status=not_selected、release=null。候选因目标无增益且出现回归而未发布。本轮已经走到真实比较，但这个单次对照不支持稳定因果或广泛泛化结论，也不能把“成功产出并验证一个候选”写成“成功提升并发布 Skill”。本补核没有重复统计费用或新增执行。
