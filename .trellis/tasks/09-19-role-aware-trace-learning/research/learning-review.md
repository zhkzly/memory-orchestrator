# 局部轨迹整理接入：独立只读审查

审查日期：2026-09-19。范围是 `learning.py` 的 `_summary_excerpts`、`_prepare_trajectory`、`_extraction_inputs` 和 `learn()` 接入，对照 v1.8.0 的 prompt/schema 与当前任务清单。未改产品文件，没有模型、benchmark、评分器或客户端接入执行。下述位置是审读时的行号，主代理修复后需重跑验收。

证据方式：静态消费链核对，加上未修改的 `tests/fixtures/gdpevo_context_train001.json` 所含 136 事件的有界故障注入。探针使用真实 `index_episodes`、`build_packet`、`build_trajectory_plan`、`_summary_excerpts`、`validate_packet` 和临时 Store；`preview` 与模型返回是显式替身，只检查编排行为，不证明模型预算实现或摘要质量。没有把仍在施工中的 evidence/model API 缺口报成缺陷。

## 发现

### F01：重组包丢弃已选工具结果，而且没有留下补读入口

**位置：** `learning.py:165–168`、`188–192`。

首个包已经按任务、失败和调用关系选出有价值的片段；局部重组时却只留下 `kind in (task, feedback)` 的原片段。其余原片段只有恰好又被局部模型选为 quote，或在成功摘要的局部包里出现，才能重新进入正文/目录。`offered` 从原包的 catalog 开始，没有把被删除的原包 fragments 转成 locator。局部计划有 scan/segment 上限，因此原包已选的后段结果可以既不在新正文，也不在可补读目录中。

这不只是“摘要丢了一些字”：原本已可用的关键返回会变成当前提取器无法请求的证据。它尤其容易损失由原先失败/恢复选择策略找到、但不在本轮前几个局部段中的材料。

**实际探针：** 对真实 fixture 使用 `max_scan_events=6`、`max_segments=3`、`max_groups_per_segment=1`；原 packet 限制不变，角色上限各 1800 字符，局部输出是 schema 合法且通过精确引用检查的少量动作/任务摘录。初始正文有 19 个 action/result 事件；重组后 15 个原结果连 locator 也不可达，最终正文角色只有 action/feedback/task，没有 observation。不可达事件包括 `observation_8`、`observation_16`、`observation_17`、`observation_32`、`observation_33`、`observation_48`、`observation_49`、`observation_66`、`observation_67`、`observation_82`、`observation_83`、`observation_98`、`observation_99`、`observation_114`、`observation_133`。返回包仍通过了既有 `validate_packet`；它证明原文未篡改，不能证明所需证据可达。

**必要修复方向：** 重组时维持已有重要原文和调用伙伴的可达性。至少把将被移除的原片段纳入有界目录候选，并使错误/验证、已选调用的真实返回及原先选中的重要材料不会排在普通目录项后被挤掉；容不下时记录具体丢失范围/原因。不要通过放宽事实引用白名单解决。

**必要验收：** 从真实 fixture 派生 scan/segment 受限情况，局部模型只引用动作。检查原先选择的关键实际返回仍在新正文或授权目录；针对能容纳的调用组检查动作与返回均可达。预算确实不足时验证明确的不可达记录，而不是仅一个泛化的 partial 文案。

### F02：后续局部调用失败时，已完成整理未收口，状态留在 planned

**位置：** `learning.py:152–161`、`162–207`、`735–738`。

局部 `call()` 的 DomainError 在该循环没有处理，直接跳到 `learn()` 外层。`report_ref` 和 segment 状态更新都在 call 返回之后，已完成的 summaries 也只在全部循环结束后才合并。一次格式修复耗尽、实际用量导致的预算超额或 transport 失败，会让已经成功的局部材料没有进入上层，失败段仍显示 planned。

**实际探针：** 同一真实 fixture，第一段返回合法摘要，第二段显式注入 `model_budget_exhausted`。观测到两个调用报告身份，但 `trajectory_processing.mode=planned`、`summary_count=0`；第一段 status=completed，第二段仍 status=planned 且没有对应 report_ref。这不是模型能力问题，是异常路径没有完成状态更新。

**必要修复方向：** 局部调用失败时先记录该段实际状态、错误/报告身份、已经完成与尚未处理的范围。已有有效局部材料应按仍可用的提取预算决定继续部分提取或明确终止；即使不能继续，也必须保留完成数量和来源，不留 planned 冒充未调用。真实失败用量仍由同一个 call/model 入口计账。

**必要验收：** 分别注入第二段格式失败、预算失败和 transport 失败。核对失败报告绑定、已完成摘要数量、未处理段清单和终态；在 summary 阶段额度耗尽而 extract 额度仍足够时，检查可用部分是否按协议进入实际 extractor。不得为了继续而重建 model 或重置累计额度。

### F03：正常局部弃权被 learn 归类为错误

**位置：** `learning.py:156–164`、`183–185`、`738`。

schema/prompt 明确允许 `LocalSummaryDraft.status=abstained`，也允许 completed 空 observations。当所有段合法弃权/空输出，或合并后的证据无法容纳时，辅助函数设置 mode=abstained 后抛 `trajectory_no_summary`。但外层只将 `evidence_budget_exhausted` 和 `model_budget_exhausted` 映射为 abstained，所以最终学习周期变成 error。

**必要修复方向：** 将“没有可用局部经验/无法在预算内提供上层证据”的正常终态与结构/来源错误区分；允许弃权的合同必须在真实调用链中得到同样分类。

**必要验收：** 全部局部调用返回 schema 合法 abstained，以及 completed+空 observations 两个例子，最终学习周期应明确弃权并保留报告/unknowns；错误引用仍走拒绝/错误路径，不能借此被吞掉。

## 已确认的正确边界

- `_summary_excerpts` 只在当前 packet.fragments 中找来源，逐 quote 检查精确子串和每条 `max_quote_chars`，按 UTF-8 字节重新计算子范围，保留原 hash/来源/结构；派生说明没有伪装成原文。
- `max_observations` 在宿主检查中实施；`abstained` 必须空 observations 来自实际 schema 校验。语义解释依然是模型判断，不能由合法 quote 自动证明。
- `_extraction_inputs` 传任务身份和已给 requirement refs，没有再次把所有完整任务正文塞进模型；相关经验的历史引用仍标记是否在当前包提供。
- summarize 使用既有 `call()`，进入同一个 model.generate、usage 和报告持久化路径。没有另建局部模型实例或通过直接 invoke 绕过统一调用入口。
- 候选修改、评价和发布路径未被此改动放宽。

## 集成时必须补验，不能由本次探针替代

1. 真正的 StructuredModel.preview 与 generate 共用完整消息 renderer；局部调用、提取、修复及补读实际消耗同一累计额度，缺失 usage 保留预留和未知。
2. 计划覆盖、实际发给局部模型的正文覆盖、成功整理覆盖和最终提取包覆盖分别核对。当前 state.coverage 拷贝的是 plan.coverage；段被进一步缩小/跳过后，不能把它当成模型已分析比例。
3. 短正文但有缺失 parent/关系歧义的例子：是否仅因 incomplete_reasons 非空就额外做摘要；确认它符合“短输入不强制增加压缩调用”的要求。
4. 从最终 packet 重新读取/展开时，摘要 quote_refs 仍只引用真实当前正文；summary/report/catalog IDs 的事实引用应被拒绝。原生可见分析只能以 intention/原source_role呈现，不能补造隐藏推理。
5. 本轮行为验收完成前，N04/N06/N11 保持 partial/in_progress；不把上述静态和故障注入结果写成模型学习效果。

## 统一入口重写后的复审

用户要求“直接重写这部分”后，主代理将学习入口改为 `_learning_packet`：先规划，再直提或局部整理。复审确认 `learn()` 不再先调用全局 `build_packet` 再可选包装；剩余 `build_packet` 只用于局部材料的限定来源缩小。非学习消费者继续使用 EvidencePacket 工具不构成旧学习路径回退。

复用了上文真实 136 事件 fixture、6-event/3-segment 参数和无模型替身，并将探针调用改为新入口。

- **F01 局部整理分支已修复：** 对本次计划实际选择的事件，新输出正文+目录不可达数为 **0**；正文包含 action/observation/task/feedback。计划的 15 项目录经去重和预算选择进入最终 11 项，未声称源轨迹其余 131 个未投影事件已经提供。短引文带入同调用且绑定无冲突的动作/返回原文。
- **F02 已修复：** 第二段注入预算失败后，第一段摘要保留，`mode=partial`、`summary_count=1`、`analyzed_packet_count=1`；第二段为 failed 且绑定错误和报告，第三段为 not_analyzed_after_stop。`planned_coverage` 与实际分析数量分开。这个探针仍只验证编排，真实 token 结算由模型预算测试负责。
- **F03 外层分类已修复：** 新的 `learn()` 收口已将 trajectory_no_summary 纳入 abstained。此项是静态分类复核，完整合法弃权集成例仍由主代理验收。

### F04：直提分支清空局部计划的续读目录（新增）

**审读位置：** `_packet_union` 清空 readable_ref_catalog；`_learning_packet` 的直提条件使用 scan_complete 和 omitted_events，而后者包含目录可见事件。

从同一真实 fixture 派生仅保留前 3 个原始事件的输入，保留事件原文及关系；将直提阈值设为可容纳。计划实际给出 `scan_complete=true`、`omitted_events=0`、`truncated_events=1`、`raw_body_complete=false`，并有 **3 个**续读目录条目。新入口返回 mode=direct，但最终目录为 **0**。超长模板只有已选前段，后续内容没有可请求的 locator。按事件计数看全部“出现过”，不表示全部正文已提供。

**必要修复与验收：** 直提并集保留受限且可用的原续读目录，或者确实要求正文完整才能直接提取。加入这个“事件已全部扫描、其中一个正文被截断”的直提回归，检查最终已给正文、目录和覆盖的语义一致，不允许以目录覆盖证明正文完整。

### 配置错误边界

当前 `_policy` 对显式 `trajectory_processing=None` 跳过校验，但统一入口随后必然按 dict 读取，导致未收口 TypeError。省略参数采用同一算法默认值是合法分支；None 不应成为隐式关闭入口。建议在配置校验阶段返回 learning_policy 错误，并测试不会留下一个已开始却无终态的学习周期。

合同同步已完成：统一入口、同算法默认参数、旁注与分支区别、计划/实际覆盖及局部失败收口写入 v1.8.0，状态保持 partial。`summarize_trace_v1` revision 2 明确 max_quote_chars 对每条 quote 生效。源包一致与生成视图 verify 已通过；这不关闭 F04 或代替最终行为验收。

## 冻结源码的最后复核

2026-09-19，对 `learning.py` SHA-256 `f0e883b1118b0d992eedbde77a9a8dc49f6013708f0b86f8ccde69d2be6dcf84` 进行针对性复核。按主代理要求仅运行新增问题对应的实际 fixture 回归，不重跑全套或修改产品。

```bash
PYTHONPATH=src:tests .venv/bin/python -m unittest \
  test_memory_trajectory_learning.TrajectoryLearningTests.test_short_projected_trace_keeps_continuation_catalog_without_summary_calls \
  test_memory_trajectory_learning.TrajectoryLearningTests.test_null_strategy_cannot_disable_the_unified_input_path -v
```

结果：**2/2 通过，exit 0**。

- **F04 关闭：** 真实 fixture 派生的短前缀保持直提、不增加摘要调用，同时保留原文续读目录及 `raw_body_complete=false` 的诚实覆盖标记。正文有截断不再造成目录被无条件清空。
- **None 配置错误边界关闭：** 显式 None 在进入学习前抛出 learning_policy，模型调用数为 0。
- **单入口检查通过：** Python AST 核对 `learn()` 只有 1 次 `_learning_packet` 调用、0 次全局 `build_packet` 调用；模块无 `_prepare_trajectory` 定义。没有回到“旧全局抽样＋可选包装”的双路径。

本审查列出的学习入口问题均已在相应复审范围内关闭。预算估计与提供方实测、模型实例累计作用域、阶段额度不保证后续可行以及元数据扫描开销仍是明确边界，不包装为学习效果。总纲状态待主代理完整回归结果后再由文档负责人同步；本次复核未提前标记 implemented。
