# Evidence / trace 复用接缝勘察

只读勘察，2026-09-19。依据当前 v1.7.1 的 N04/N06、`evidence.py`、`trace.py` 及真实 fixture；未跑模型、benchmark 或产品测试。读取时新任务 PRD 仍有 TBD，implement.jsonl 为空，design/implement/resume 尚未建立；以下是供根代理定稿的接口建议，不是已经实施的契约。

**可复用原始索引、精确范围读、引用校验和补读；需要补的是严格分块输入、角色投影政策，以及组内目标/修订一致性。** 不需要另建一套 trace 格式或独立存储框架。

## 1. 已有数据路径及可直接复用的接口

| 位置 | 实际职责与复用边界 |
| --- | --- |
| `evidence.index_episodes` L98–242 | 校验同项目 Episode；内嵌事件与磁盘 `TraceRecords` 共用 registry。原文、角色、kind、task/goal/revision、call/parent、resource 均保留；反馈仅允许 adaptation。磁盘索引未完成返回 `needs_index`，不能拿空 events 当完整轨迹。 |
| `trace.import_trace` / `ensure_trace_index` L48–196 | 冻结 JSONL，按显式 max_events/max_bytes/max_event_bytes 推进；SQLite 保存元数据，独立 text spool 保存解码后的 text。无需把磁盘正文整体构造成 Python 字符串。 |
| `TraceReader.rows/get_metadata/read_range` L222–272 | 元数据可按 position/SQL 条件有限查询；正文按解码 UTF-8 字节范围读取，校验1024字节块 hash。是新分块器的读取底座。 |
| `TraceRecords.matching` L321–335；`evidence._matching` L357–367 | 同 episode 的 call 伙伴、用户目标事件、资源关联可复用；当前无 task/goal/revision 筛选参数。 |
| `_piece/_pieces/_resolve` L278–336 | 生成或回读精确源片段。`ref_id=base_ref:start:end`；范围属于事件 text 的 UTF-8 字节，不是 JSONL 行偏移。`source_record.raw_range` 才是序列化行坐标。 |
| `build_packet` L583–692 | 有界选取、组内动作/返回端点、目录、关系投影；当前是全 index 的选择器，不是遍历全轨迹的 chunk iterator。 |
| `validate_packet` L695–743 | 对正文、hash、范围、source structure、绑定、关系和 coverage 从原索引重建核对。继续作为新投影的最终验证器。 |
| `expand_packet` L746–774 | 只扩当前目录中的未读引用，保留既有正文，再验证新包；不能任意跳读，更不构造总结。 |
| `validate_citations` L777–801 | 引用只允许当前 packet 已给正文；目录不能充当事实。检查可见性，不证明语义或因果。 |
| `feedback_view` L804–829 | 反馈身份、状态、结果与已给片段绑定；长 reason 不绕开 packet 预算。新局部流程应继续消费它。 |

源文件：[evidence.py](../../../../src/memory_orchestrator/evidence.py)、[trace.py](../../../../src/memory_orchestrator/trace.py)。

registry 的关键字段已有：`base_ref/episode_id/event_id/source_kind/source_role/namespace/position/task_id/goal_id/task_revision/call_id/parent_event_id/parent_episode_id/resources/raw_ref/raw_hash`。磁盘记录另有 `text_start/text_bytes/source_record`，不含整段正文。不要往 registry 写派生摘要再假装原事件。

## 2. 角色投影的最小改变

当前 `_kind()` 是语义选择标签：所有 instruction→task；note 通常→observation，含恢复/反例词又会改变标签。因此不能直接把 `kind == task` 当“用户要求”，也不能把 `kind == observation` 一律当低价值工具噪声。[evidence.py L76–95](../../../../src/memory_orchestrator/evidence.py)

建议新增一个纯内部 `learning_role(record)`，只读原 `source_kind/source_role/namespace`，返回 `user/action/note/result/feedback/unknown` 及判定依据，不覆盖原字段。来源缺失继续 unknown；agent 自述不能升格为用户要求或外部结果。

角色政策决定保留完整原文还是较短范围，不能决定事实真假：

- user 与 requirement：优先保留约束；`namespace=requirement, position=-1` 只是 Episode 任务元数据，不能追溯支配早期其他 revision。真实用户锚点另保留。
- action：保留工具名、参数和源绑定；超长命令同样受预算，不偷偷全放。不得只留请求、丢掉真实返回。
- note：明确是 Agent 显式笔记/自述，可较强压缩；不是隐藏推理，也不是验证结果。
- result：可以投影，但真实关键值、失败、恢复和最终产物不能仅因角色排序被全部挤掉。沿用原文精确范围；不能重排 JSON 字段后沿用旧 ref 假称连续原文。
- feedback：继续单列实际 binding/outcome 与来源，不被 note/result 降级政策误删。

每角色的范围上限须由本轮显式 policy 提供；这些上限和投影说明进入局部模型输入。`_fits()` 仍检查包含 metadata 的包，总 token 目前是 `ceil(UTF-8 JSON bytes/3)` 估算而非真实 tokenizer 计量。

## 3. 当前“成组”不等于完整交互分块

`_selection_units()` L555–580 以 `(episode_id, call_id)` 取伙伴，非 call 事件单独成组，防止按相邻位置误配。`place()` L619–644 尝试整组片段，放不下时可给动作正文和返回 locator。需要保留这一机制，但明确三个差异：

1. 同 call 的所有结果可能因 metadata cap 被截断；`relations.calls.coverage` 会反映端点不全，不能把候选 members 当完整原调用集合。
2. `coverage=complete` 目前表示端点已给正文或可读 locator，**不表示全部结果正文已读取**。分块器还需独立记录正文覆盖。
3. 组键没有 task/goal/revision；已知相互矛盾的身份不会自动拒绝分组。新局部提炼必须检测它们，而不是让模型从“成组”推断同一个要求。

建议以 call 组为最小交互单元，按首次源 position 安排 chunk；并行交错的返回按 call ID 拉回对应组，而非把一个连续文本区间当完整工具交互。user 锚点、显式 parent 关联的 note、匹配 revision 的反馈作为本组上下文。缺 call/parent 身份时保留独立事件和缺口，不根据相邻位置虚构因果。

迟到结果即使出现在切换目标之后，仍应保留其明确声明的旧 revision。若动作与结果的已知绑定冲突，保留调用关联、标 binding ambiguity，不将结果强配到新目标，也不能拆成两个假“完整”调用。一个超大结果可有多个同源范围，但须保持 group 身份及 partial 标志；整组永远无法在预算内完整提供时返回明确缺口，不无限重试或静默丢组。

## 4. 最小接口建议：一个有界遍历接口，一个受限装包入口

下面是建议形状，不增加注册器或通用查询 DSL：

```python
iter_interaction_groups(index, *, episode_id, after_position, max_groups, max_records)
# → {groups, next_position, complete, gaps}
# group: {member_refs, source_positions, observed_bindings, binding_status,
#         call_status, endpoint_coverage, user_anchor_refs}

build_packet(index, *, limits, focus_refs=(), dependency_limits=None,
             selection=None, role_policy=None)
# selection=None 保持现有调用；有selection时严格限定本块的原文范围/组及显式锚点。
```

`iter_interaction_groups` 只走有界元数据页、按 call ID 查伙伴，再按预算读必要正文。优先复用 `TraceReader.rows(position > cursor, limit=N)` 和现有 SQLite call 索引；内嵌事件用相同次序/分组规则。必要的 goal/revision 过滤使用已有 SQLite 列，不新建第二份原文。

**不要仅在每轮给 `focus_refs`。** 当前 focus 只是优先级，`_metadata_candidates` 还会加入全 index 其他事件；那样每块可能重复同一批高优先片段，既不完整也不覆盖剩余轨迹。严格 selection 应同时约束候选、目录和自动 dependency 扩展。跨目标反证可另外作为明确相关材料给出，不能悄悄混成当前目标的执行过程。

`expand_packet` 的公开形状可保持：目录由本块受限装包器产生，它继续按原引用展开。装包公共骨架、`_refresh`、`validate_packet` 只保留一份，避免新局部路径复制后与旧路径漂移。

缺标目标已有 [`goals.associate_goals`](../../../../src/memory_orchestrator/goals.py) 的 `index.goal_annotations`，是 `origin=model_proxy` 的旁注，不能改写原 task/revision。新分组若消费它，应同时保留 observed 与 derived binding，不把派生身份伪装为源日志。

## 5. 局部摘要不能冒用原文身份

重排原文片段不会破坏引用；改写 fragment.text 会被 `validate_packet` 拒绝。这条应保持。局部结构化整理应是独立派生产物，带 `source_refs`，使用原局部 packet 做引用校验，不取代原 fragments。

当前 `validate_citations` 只允许**本次包**已给的 refs。若下一层只读摘要、没有读底层原文，则不能把下层读过的 ref 直接宣称为上层已提供。根代理需要在设计中明确：关键原片段继续随摘要进入下一层，或建立单独的、诚实标为派生证据的验证路径；不可直接放宽现有 whitelist 把全部原档当已读。这是 learning/新整理 schema 的交接点。

## 6. 磁盘与预算的实际边界

- `ensure_trace_index` 每次会流式 hash 全原档，恢复时也核对派生文件；“不全读”应指不整体载入内存/模型，不应声称没有全文件校验 I/O。
- `TraceReader.set_read_budget` L208–214 当前只限制缓存大小，不限制累计读取字节；`stats.body_bytes/range_reads` 可用于新累计账本。局部分块数量/正文读取/模型输入须分别限额，不能每块重置全局学习预算。
- 单个 JSONL 事件超过 `max_event_bytes` 或该批 max_bytes，会先被索引挡住。索引后的角色投影不能修复这一点；保留可恢复缺口，不自行突破源读取限额。
- `TraceRecords.values/items/__iter__` 会流式遍历全部元数据；不要 `list(index['records'].values())` 再造巨型候选集。现 `_bindings` 与某些 goal transition 会扫元数据，虽不读全正文，但每 chunk 重复调用有成本；可缓存确定的绑定目录，不缓存全正文。

## 7. 现有测试与新增验收建议

| 可复用测试 | 必须保留/补足的行为 |
| --- | --- |
| `test_memory_evidence` 的 call_pairing / structure / relationship_metadata | 非相邻与并行交错调用、已知 parent、篡改 role/call/position 拒绝；新增多 result 超块上限仍 partial，已知跨 revision 冲突不能当同目标。 |
| 同文件的 goal_switch_resume / later_user_revision / goal_suggestion | A→B→A 与真实修订分开；用户锚点不能由 agent note 代替；新 chunk 不继承最终要求。 |
| 同文件 long_trace / expand_only_catalogued / catalog_not_citable | 超长单事件保持精确 UTF-8 范围；假摘要替换 text、未读 locator、外项目引用继续拒绝；新增局部→全局摘要引用边界。 |
| `test_memory_trace` resume_reopen / tamper / malformed / byte_budget | 磁盘冷开与增量推进、禁止全文件 read_text、原档篡改拒绝；新增元数据分页及真实分组 inline/disk 等价，不把缓存上限当累计 I/O 限额。 |
| 同文件 actual_learn_waits / frozen_parent / transitive_source_eligibility | 索引未完成、隐藏 final 父链必须仍在任何局部模型调用之前拦截。 |
| `test_gdpevo_context` 五个真实 fixture 回归 | 136事件、67动作/67工具返回、1用户/1最终环境结果；原42,000字符/1,800片段/24目录预算可作旧路径回归。新增分块后真实产品/库存结果仍可达、模板续段及8项SP完整，不能仅保留actions。 |

真实 fixture 没有 note 事件，不能靠它证明 note 降采样与目标歧义；补独立构造例，不修改原 fixture 的来源或期待模型学会规则。局部多调用的累计预算/真实 messages 交接应在 `test_memory_learning` / `test_memory_model` 增加集成断言，由相应实现方负责。

文件入口：[test_memory_evidence.py](../../../../tests/test_memory_evidence.py)、[test_memory_trace.py](../../../../tests/test_memory_trace.py)、[test_gdpevo_context.py](../../../../tests/test_gdpevo_context.py)。本勘察仅静态核对，未将此前测试通过记录当作新功能验收。
