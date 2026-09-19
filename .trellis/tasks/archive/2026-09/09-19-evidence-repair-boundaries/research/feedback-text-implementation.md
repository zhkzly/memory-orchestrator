# Feedback.reason 原文视图实施记录

前半部分记录首次实现及其检查；后续完整适配检查发现双视图挤压，最终实现以文末“同源共享正文修正”追加为准。不能将首次相关回归通过当成全部集成通过。

## 责任与范围

实现节点 N04/N06，任务依据为已审核 design/implement/resume；总纲从 v1.8.0 同步到 v1.8.1 由其他代理负责。本代理只修改 `src/memory_orchestrator/evidence.py`、`tests/test_memory_feedback_text.py` 和本记录。未修改 learning/model/schema/prompt、配置、评分器、选择或发布规则；未发出网络/真实模型调用，未 commit。

框架提供机械可读的固定字段来源，模型仍负责选择引用与语义判断。实现没有替模型修正 quote、解析 reason 内部 JSON 或降低精确子串校验。

## 实现

- 旧 full Feedback 的 base、text、hash、raw_ref 和 UTF-8 坐标完全保留。
- 非空 reason 新增一个固定 `reason-text-v1` 身份：`digest([project, episode_id, "feedback", check_id, "reason-text-v1"])`，`raw_ref=feedback:<check_id>#/reason`，正文严格等于原始字符串，hash/range 针对该字符串。
- namespace 仍为 feedback，event_id 仍为 check_id，source_event 仍为 false。既有 `feedback_view` 已按反馈身份汇集 refs，无需修改或新增无消费者字段。
- `_refresh` 的必需记录数和已提供必需记录集合都排除附加字段视图；原有 full Feedback 或原始事件缺失时不能由 reason 替补。附加字段的裁剪也不令一份原来完整的旧包失效。
- 只扫描 in-memory registry 来计固定字段视图；磁盘源不因覆盖统计而全量物化。选择、分段、正文/目录预算与补读限制均保留。

## 红灯与预许可

1. 新测试文件初始 11 项：9 项在“无独立 reason 来源”处失败，空字段/禁学反馈 2 项通过，命令 exit 1。
2. 从 `gdpevo_summary_repair_train001.json` 载入真实输入/拒绝稿，旧 `_summary_excerpts` 仍返回与归档一致的 4 条 `summary_evidence` 错误；随后对新字段来源的验收失败，确认需求缺口。测试比较 `DomainError.details.errors` 与归档 envelope 的 `diagnostics.errors`，不把 envelope 额外 code/message 当错误明细。
3. 修改产品前，官方 `mutation_license.py` 以既有 `test_memory_evidence.EvidenceTests.test_packet_cannot_relabel_revision_feedback_or_budget` 为验收，将 `if item[key] != expected[key]:` 临时改为 `if False:`。工具确认原始绿→注入红→内部按字节恢复绿，exit 0。没有 git 还原。

## 最终验收

```bash
PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_feedback_text -q
```

15/15 通过，0.292 秒；覆盖独立身份、旧 full 原文、错误 ref/伪造 quote、真实拒绝稿、多语言 UTF-8、合法 JSON 的空白/键顺序、hash/range/origin/structure 篡改、目录未读/补读预算、旧完整包读取与扩展、覆盖分母与缺失义务、反馈聚合、参考轨迹 role/packet cap、磁盘无全扫描、final/selection 禁学和空 reason。

真实拒绝稿检查保持 5 个 quote 字符串不变：outcome 使用原 full ref，4 个 id/matched 子串使用新的已提供 reason ref，全部可从 index 按精确字节范围回读。这里构造的是合法引用测试，不代表模型已经在实盘正确改用了 ref，也不证明整段叙述语义或归因正确。

```bash
PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_feedback_text test_memory_evidence test_memory_trajectory test_memory_trajectory_learning test_memory_model_budget -q
```

98/98 通过，8.375 秒，exit 0。`git diff --check -- src/memory_orchestrator/evidence.py tests/test_memory_feedback_text.py` 与 `python3 -m py_compile src/memory_orchestrator/evidence.py tests/test_memory_feedback_text.py` 均 exit 0。

## 容量回归首差与处理归属

首次相关 83 项回归：82 通过，1 项 `test_disk_and_inline_group_projections_match_without_whole_text_load` 失败。没有直接改产品来追求测试绿。

- 首个被拒的磁盘 placement：31,764 字符；max_chars=42,000，reserve=10,500，实际阈值 31,500；该候选 source_record 值合计 2,474 字符。
- 第一段最终 inline 31,135 字符，disk 33,942 字符；后者包含后续不预留 reserve 的目录填充，所以最终大小不能当先前 placement 阈值。
- 唯一 inline 额外正文为 `ev:1e82ebdd804ba1c079d45381:0:492`，原文 `run_af2c81d1463e48f3a931a8ebc78239e6:events:7`，hash `32e1a3cfe924d41e584b42ce874efdb923a428e93f430eaafe0e63be915d2483`；disk 无额外正文。
- 仅诊断将两个输入的 max_chars=80,000/token_budget=40,000 时，全部 segment 的 event_id/range/text/顺序一致。这是合法来源表示大小不同触发容量裁剪，不是来源内容或调用分组不一致。
- 根代理审核后单独修改旧等价测试的非绑定容量前提，保留禁止全文加载和有限扫描检查；本代理未改范围外测试。生产预算和策略未变。新测试仍保留 9,000 字符限额与 100 字符补读拒绝路径。

参考配置应用于保存的 136 事件 fixture：4 个局部包均包含 full/reason 各 1,600 字符且整包不超过 15,000 字符；feedback_view 每包只有一条反馈。该探针投影 8 个事件、截断 4、遗漏 128，stop=segment_budget。这说明新增正文真实占用容量；不能把两种反馈表示的重复内容当额外独立证据。

## 官方 mutation：14 个关键不变量全部获得许可

各次均调用 `/home/kelong/ai-workbench/tools/mutation_license.py --target src/memory_orchestrator/evidence.py --tests "PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_feedback_text.FeedbackTextTests.<对应方法>" --mutate <单点文本替换>`；原始绿→注入红→工具按原字节恢复绿，全部 exit 0。注入均局限于独占 evidence.py，恢复不使用 git。

| 注入 | 杀死它的验收方法 |
| --- | --- |
| 禁止创建 reason view | test_real_reason_has_an_independent_exact_field_identity |
| full Feedback text 改成 reason | test_old_full_feedback_bytes_and_identity_are_unchanged |
| reason-text-v1 身份种子改成 v0 | test_real_reason_has_an_independent_exact_field_identity |
| 将 reason parse 后重新 JSON 序列化 | test_json_reason_keeps_original_spacing_and_key_order |
| reason hash 错用 full hash | test_real_reason_has_an_independent_exact_field_identity |
| reason 标成 source_event=True | test_feedback_metadata_and_event_counts_are_not_duplicated |
| required_count 包含附加 view | test_old_complete_packet_stays_readable_and_complete |
| selected_required 错用全部 selected | test_reason_view_cannot_replace_unread_full_feedback_or_an_event |
| 附加 view 的短片段算原始记录截断 | test_reason_view_cannot_replace_unread_full_feedback_or_an_event |
| 跳过 adaptation visibility | test_final_and_selection_feedback_have_neither_view |
| 跳过 raw hash/range/origin 对账 | test_tampered_field_text_hash_range_and_origin_are_rejected |
| feedback_view 对每个反馈迭代两遍 | test_feedback_metadata_and_event_counts_are_not_duplicated |
| _fits 无条件接受 | test_field_continuation_must_be_read_and_counts_against_budget |
| UTF-8 长度错误改成字符数 | test_multilingual_reason_is_unparsed_and_uses_original_utf8_offsets |

## 剩余限制

这里只修原始字段的呈现和来源坐标。模型可能仍选错 ref、提出无根据观察或不生成有用经验，需要后续真实回放保留结果。双视图可能挤占其他局部正文；本任务没有改选材算法或凭空增加单包预算。准确引用也不等于因果成立、Skill 有效或已经发布。

## 同源共享正文修正（最终实现）

完整 GDPevo 适配检查另有 33 项中 1 项红灯：原 42,000 字符预算下，磁盘 packet 丢失 orders 返回。首因是同一反馈的 full/reason 被当两个高优先级单位，各占 1,800 字符正文。首次 orders 放置从 29,731（仅 full）变成 32,435（双视图），超过扣除 reserve 后的 31,500；新增量 2,704 正是 reason 片段及分隔符。该问题属于新增表示的重复选材，本次没有再修改业务测试或扩大预算。

根代理审核并授权一般性修正后：

- `_selection_units` 按同 episode/check_id 合并反馈的两种视图，仍从候选/allowed_refs 边界内取成员。它们共享原单条反馈的 `min(max_fragment_chars, feedback role cap)` 正文额度。
- full 默认只取 `reason` 字段之前的精确原文前缀，长度动态计算；控制片段最多占本单位一半。头部过长时退为原 full 中 `outcome` 字段的精确子范围；若它仍超过一半，则正文优先给 reason，full 仅在目录容量内保留补读定位。
- reason 使用剩余额度；全部来源元数据、目录和正文仍由既有全包计费。显式只允许一个视图时保持该视图原有裁剪/补读行为，不自动引入兄弟。原 full 索引与原字节范围没有改变。
- 没有修改业务 family、评分点、模型语义、配置或发布门，没有设置 650 等 fixture 常量。

只读内存探针在原 42k/片段 1800 下采用 full 650 + reason 1150，得到 41,755 字符 packet，恢复 orders/products/inventory/customers，SP001–008 全部可见，旧 full 目录展开通过。当前摘要 1600 额度为 full 650 + reason 950，真实拒绝稿 5 个原 quote 在正确 ref 下均通过；数字仅为该固定材料的容量证据。

正式实施前，已有 15 项绿验收对 selection 屏蔽 reason 的注入取得官方许可。随后新增 5 项先跑：共享单位、角色共享上限、超长 metadata、极小额度 4 项红；单视图显式选择 1 项原本绿。实现后另补一条“元数据超过半额但未超过全额”的边界，总共 21 项全部通过（0.354 秒）。

最终相关回归（当时 20 项新反馈测试 + 83 项相关 memory + 5 项原 GDPevo context）：

```bash
PYTHONPATH=src:tests .venv/bin/python -m unittest test_memory_feedback_text test_memory_evidence test_memory_trajectory test_memory_trajectory_learning test_memory_model_budget test_gdpevo_context -q
```

108/108 通过，16.274 秒，exit 0；包含原 `test_real_trajectory_disk_index_keeps_the_same_useful_call_categories` 的固定 42k 要求。之后新增半额边界的反馈单文件为 21/21；完整总套由根代理统一执行。

本次再获得 7 个官方 post-mutation 许可（原始绿→注入红→内部字节恢复绿，全部 exit 0）：

| 注入 | 验收 |
| --- | --- |
| 把同 check_id 的两个 view 改成独立选择 key | test_two_views_share_one_selection_unit_and_body_allowance |
| reason 不扣除元数据已用额度 | test_role_cap_is_shared_even_when_fragment_cap_is_larger |
| 元数据允许占全部额度而不是最多一半 | test_metadata_over_half_uses_outcome_without_starving_reason |
| outcome 原文 start 错用字符坐标 | test_long_metadata_uses_exact_outcome_range_and_preserves_reason_budget |
| 极小额度仍塞入 full 正文 | test_tiny_feedback_allowance_prefers_reason_and_keeps_full_locator |
| 极小额度不提供可容纳的 full 补读目录 | test_tiny_feedback_allowance_prefers_reason_and_keeps_full_locator |
| 单视图错误进入双视图共享分支 | test_explicit_single_view_selection_does_not_pull_in_sibling |

截至此处，本代理共 21 个 post-mutation + 2 次修改前许可，均使用官方工具、只临时修改 evidence.py、内部恢复。源与测试已向根代理发出冻结信号；没有自行启动实盘或提交。此次确定性检查仍不证明模型实际选择正确、经验有效或发布成功。
