# A 实现与验收记录

所有权：`src/memory_orchestrator/evidence.py`、`tests/test_memory_trajectory.py` 及本目录证据。没有修改 trace.py、公共 JSON、learning.py、model.py 或发布器；没有运行真实模型或 benchmark。

## 已落接口

```python
build_trajectory_plan(index, *, limits)
# {segments:[EvidencePacket], segment_scopes:[...], coverage:{...}, read_stats:{...}}
build_packet(index, *, limits, focus_refs=(), dependency_limits=None,
             allowed_refs=None, role_max_chars=None)
```

`allowed_refs` 是严格的原始事件 base_ref 集合：正文、调用组成员和目录均不得跳出；空集合返回无可容纳证据的 DomainError，不回退全索引。原有 focus 仍只代表优先级，供其他已有消费者使用。

新 limits：`max_scan_events/max_segments/max_groups_per_segment` 三个正整数；`packet` 为原 `max_chars/max_fragment_chars/max_catalog_refs/token_budget`；`role_max_chars` 为 user/action/note/result/feedback/unknown 六个正整数字符上限。角色不改写源字段，可见 note 不变成事实或用户目标；错误/恢复结果采用受保护的诊断长度。

## 实际选择与分块

- 先有界扫描事件元数据，按 episode+call_id 分组；没有 ID 的事件独立保留。已知目标/修订冲突为 ambiguous，缺失为 unknown；派生目标旁注不覆盖已知源身份，同一事件的冲突旁注不采用最后一条覆盖。
- 同绑定、连续组构造候选段；跨绑定分段。段级优先级在 max_segments 截止之前执行：0=实际反馈/错误提示，1=user/恢复/反例，2=末端源事件，3=action，4=可见 note，5=普通 result。同优先级保持原次序。原文片段在已选段内按 source_position/字节范围排序。
- user/requirement 的初选正文始终从原文开头开始，不能让用户粘贴的日志 ERROR 把控制要求挤到目录。工具/反馈仍支持错误位置锚点。大用户材料仍有字符上限和续段引用，不全量塞入。
- 重复普通工具结果可移至自身 locator，保留调用身份和缺口；重复错误不折叠。只有已有正文代表的结果才进入去重集合。零执行事件但有 requirement/独立 feedback 时仍生成控制材料段，不虚构执行。
- 磁盘与内嵌同源投影对照发现已有反馈 position 使用空 header events 长度；现统一使用该 trace 的实际 event_count，保证派生反馈位置同形。

## 覆盖和成本口径

`projected_events` 为有正文的唯一源事件；`folded_events` 为本轮明确折叠的重复结果；`omitted_events` 为连正文/目录端点都未提供的源事件；`truncated_events` 为有正文但范围合并后仍不完整的事件。`raw_body_complete` 仅表示原事件正文范围覆盖，不证明任务或推理正确。

`max_scan_events` 只限制选择扫描，`coverage.scan_limit_scope='selection_events'`。绑定/关系核验可能读取更多元数据；真实额外工作记为本次 `read_stats` delta（body_bytes/range_reads/metadata_rows）。这些读计数不含此前归档 hash 的完整流式校验，不承诺总 I/O 上限。未用未经验证的缓存掩盖读取。

真实136事件 fixture 的覆盖型测试参数为 scan512/segments24/groups6、packet42000字符/片段6000/目录24/token估算24000、roles4500/2400/600/1800/5000/800。实际产生13段、最大27289字符、总288940字符，所有136事件有正文，3事件正文仍截短。**这不是节约token的实验**；该参数只是验收覆盖配置，不是产品默认。真正摘要调用由主线程统一累计预算控制，未执行段保留 partial。

## 验收证据

- 新API首轮9项RED：`evidence-red.txt`，缺少 plan/allowlist 接口。
- 段级择取RED：`evidence-priority-red.txt`，小段数预算漏掉晚期失败；段内源序RED：`evidence-order-red.txt`。
- 无执行事件但有反馈RED：`evidence-no-events-red.txt`。
- C独立发现的 user 控制前缀案例原样派生RED：`evidence-user-prefix-red.txt`；不是修改期待去迁就原错误锚点。
- 先前46项evidence/trace/真实fixture与新分块联合检查通过，见 `evidence-focused-green.txt`；追加控制材料/关键诊断及C前缀修复后，当前15项新验收加evidence/GDPevo旧验收共39项通过，见 `evidence-postreview-green.txt`。最终 learn/全套集成由root在统一入口稳定后执行。
- 初始官方原文守卫执照：`evidence-initial-license.{json,txt}`。
- 完成后18项官方mutation全部检出，每项exit0且目标逐字节恢复。执行脚本 `evidence-mutations.py`，完整命令、before/after hash见 `evidence-mutation-results.json`，原始输出见 `evidence-mutation-*.txt`。未放松验收，没有失败后继续注入。

最终 evidence.py SHA-256：`5229d0ea1c6eed6a35ba5a4830685618282f1043601e9cd3c7e8aa04c51c0ca7`。本记录不能代替后续真实学习效果或全流程验收；摘要/quote回源、模型完整输入累计预算和唯一新学习入口由root及对应worker负责。

## 追加：依赖消费遗漏的最小修复

重写审查确认旧 `learn` 的有界邻域选择没有进入新 plan：真实fixture前9事件派生资源写入者/后续ERROR检查（补充构造的资源声明）时，独立旧build_packet能提供写入者，新learn开启/关闭dependency_lookup却都遗漏它。这里不声称原GDPevo日志本来就执行了CSV写入；该派生例只隔离依赖消费行为。

已接接口：`build_trajectory_plan(index, *, limits, dependency_limits=None)`。在选定span的required集合后复用既有 `_dependencies`，再纳入严格allowed集合。root负责把 `policy.dependency_lookup` 从实际学习入口传入，并已报告 summary→extract 真实渲染输入的开关对照GREEN。

- `max_events` 是全plan新增unique neighbor余额；已提供/已计入的引用不重复扣。`max_hops`保留每条回找链的深度上限，不误扣成span调用次数。没有新联合BFS或检索层。
- `_dependencies`只新增内部可选ordered收集器，保留既有返回set与旧调用，避免共享余额过滤时丢失其发现顺序。
- `segment_scopes` 增加 `dependency_support`（原event_ref/event_id/source_scope/resources、scope_relation、availability）及 `dependency_gaps`；不同或未知scope、同episode的不同版本仍是明确候选对照，不改原事件身份、不冒充当前状态。
- coverage新增：`dependency_discovered_events`=新计额度的唯一邻居；`dependency_provided_events`=其中有实际正文的邻居；`dependency_support_events`=候选支持中有正文或目录端点的唯一事件（可含免费复用）；`dependency_omitted_events`=已选支持却无正文/目录的事件。放不下明确标 `dependency_packet_budget`。
- 新增8项接缝边界（资源、共享余额、深度、免费复用、父事件、跨版本/目标、未知scope、放不下），23项trajectory测试GREEN：`dependency-green.txt`。初始3项RED：`dependency-red.txt`；此前真实learn差异已原样发送root。
- 新增8/8官方mutation全部检出，逐项精确恢复；命令脚本 `dependency-mutations.py`，完整命令/退出码/hash为 `dependency-mutation-results.json`，每项原始输出 `dependency-mutation-*.txt`。没有放松断言。

依赖修复后冻结 SHA-256：`b4e783b65359b141c06cd912ce28642873719e80e9db4b4b2b645a21f254ada1`。所有变异窗口已释放，无遗留进程；evidence与新测试不再更改，root执行最终全套与提交。
