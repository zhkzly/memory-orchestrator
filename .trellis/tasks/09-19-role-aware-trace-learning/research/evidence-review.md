# 轨迹预处理独立审查

审查时间：2026-09-19。只读审查，不评价本代理编写的 model；未改产品、运行模型/benchmark 或启动子代理。实际检查的 `evidence.py` SHA-256 为 `0828257c5cac3674d1e36fc17f9ea02388370a41d622050391f670ae92cd7b04`，下列 probe 运行前后相同。A 的晚期失败优先和零事件 control-only 段已经存在，不再重复当作缺陷。

现版本实际使用 `learning_role`、`_role_width`、`build_trajectory_plan`；没有 `_role_piece` 函数。角色控制了片段宽度与段级优先，但首个片段仍由共享 `_pieces` 决定。

## 已证实的问题

### E01 / P1：用户材料中的 ERROR 能把明确用户要求挤出首层正文

**根因**：[learning_role](../../../../src/memory_orchestrator/evidence.py#L587) 将所有 user 来源归为 user；[_role_width](../../../../src/memory_orchestrator/evidence.py#L605) 只限制宽度；[build_packet 的 piece](../../../../src/memory_orchestrator/evidence.py#L656) 仍拿 `_pieces(..., extra=0)` 的第一个候选。[_pieces](../../../../src/memory_orchestrator/evidence.py#L291) 对 user、action、note、result 使用同样的 failure/recovery 锚点规则。因此即使用户要求在开头，后面的引用日志带一个 ERROR，实际优先正文会跳到日志附近。

**真实 fixture 派生输入**：取 `gdpevo_context_train001.json` 前 3 个事件，只修改第一个 user instruction 的正文为：

```python
control = 'USER_CONTROL_KEEP: keep only Q3 rows and never modify the original CSV.'
text = (control + '\n<quoted_business_log>\n' + 'row,ok,0\n' * 1800
        + 'ERROR: this is quoted historical material\n' + 'row,ok,0\n' * 100
        + '\n</quoted_business_log>')
```

按现有 `trajectory_limits()` 运行得到：

```json
{"role":"user","provided_control":false,"provided_error":true,
 "provided_starts":[15169],"catalog_start_zero":true,
 "coverage":{"total_events":3,"scanned_events":3,"projected_events":3,
 "folded_events":0,"truncated_events":2,"omitted_events":0,
 "scan_complete":true,"raw_body_complete":false,"stop_reasons":[]}}
```

**影响**：第一层局部整理拿到引用材料的错误上下文，没拿到这次用户明确新增的控制要求；要求虽能从目录补读，但当前方法把“用户要求优先”变成了“用户文本里词法错误优先”。这不是要求无界保留全部大输入，也不是断言最终模型一定答错；可直接证伪的是正确的控制前缀没有进入当前模型正文。

**最小验收/修正方向**：在同一大 user message 同时包含开头控制与后段引文错误时，优先保留控制前缀及其身份，正文材料按预算截取/导航；不要沿用工具结果的错误定位规则改写 user/action/note 的首片段。对没有可信结构边界的任意自然语言，只能称默认角色规则，不能声称已经准确识别全部“要求 vs 材料”。A 当前大用户测试仅验宽度与 source_role，没有检查被保留的是控制要求还是材料。

### E02 / P2：max_scan_events 只限制候选集合，磁盘路径仍反复扫描全量元数据

**根因**：[_trajectory_records](../../../../src/memory_orchestrator/evidence.py#L762) 本身按 `max_scan_events` 读取；但每段随后调用的 [build_packet](../../../../src/memory_orchestrator/evidence.py#L634) 与 [validate_packet](../../../../src/memory_orchestrator/evidence.py#L940) 都调用 `_bindings`。[_bindings](../../../../src/memory_orchestrator/evidence.py#L342) 对磁盘 episode 调用整个 `matching(episode_id=...)`，`TraceRecords.matching → TraceReader.rows` 没有限量。段数与校验次数增加，会重复遍历全量元数据。

**输入**：同一真实 136 事件 fixture 导入临时 Store；完成正常索引后，reader 的三个统计量均为 0；只运行 `build_trajectory_plan(max_scan_events=3, max_segments=1)`。

**实际输出**：

```json
{"before":{"body_bytes":0,"range_reads":0,"metadata_rows":0},
 "after":{"body_bytes":5813,"range_reads":13,"metadata_rows":450},
 "coverage":{"total_events":136,"scanned_events":3,"projected_events":3,
 "folded_events":0,"truncated_events":1,"omitted_events":133,
 "scan_complete":false,"raw_body_complete":false,"stop_reasons":["scan_budget"]}}
```

**影响与边界**：不能把 plan 的 `scanned_events=3` 当成真实只读取了 3 条元数据的证据。这个 probe **没有**读取全部日志正文（正文仅 5813 字节），也未发现把未读正文当事实；缺口是候选扫描预算与实际全局绑定扫描的消费边界不同。对大盘上轨迹，重复全量元数据遍历会放大预处理成本，当前的“禁止 Path.read_text 整读”测试发现不了。

**最小验收/修正方向**：记录/断言实际 `metadata_rows`，明确选择扫描和全局绑定读取的区别；全局绑定可利用已有索引的去重元信息或一次读取结果，避免每段重扫。若保留这一次全局步骤，则应显式计量并披露，不能宣称 `max_scan_events` 限制整个预处理的元数据工作。无需新增通用 I/O 调度器。

## 当前可认可的边界

- 动作/返回按 `(episode_id, call_id)` 归组，不按文本相邻猜配对；跨修订冲突的 call 被标为 ambiguous 并单独成段。配对关系 complete 只表示正文或目录端点可达，不等于返回全文已读。
- `_group_binding` 没把 episode 最终 revision 自动填到缺标事件；来源已知的目标/修订分段，冲突的派生注释保留歧义。
- 可见 analysis 保留 `source_role=agent` 和 `source_kind=note` 等原元数据，按 note 上限供给；代码没有补造隐藏推理。它是否被模型正确当作主张/意图，仍取决于后续实际消费者，不由角色字段单独证明。
- 本次读取版本已有段级重要性排序：扫描范围内的晚期 failure/feedback 可以排到早期普通段之前。`max_scan_events` 之外的末尾事件仍未被扫描并计入 stop_reasons，不应宣称该排序能找回扫描范围外的失败。
- 重复普通 tool result 被折叠后仍有自身原文 locator/call 身份及 gap；关键失败正文不按普通重复折叠。无重复的普通回执目前主要靠角色长度额度，并不等于任意低信息正文都能语义压缩。
- 总体 coverage 分开 projected/truncated/omitted、scan_complete 和 raw_body_complete。上述 E01 中 omitted_events=0 仍不表示要求正文被提供；消费者必须同时看范围截断和目录，不能只看单个计数。
- 大磁盘正文仍走范围读取和 chunk 校验，没有在本 probe 中出现全正文装入模型；E02 明确是元数据工作问题。

## Probe 复现命令

在仓库根目录运行；只创建随后删除的临时 Store，不调用模型：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python - <<'PY'
from pathlib import Path
import copy, hashlib, json, tempfile
from memory_orchestrator import evidence
from memory_orchestrator.trace import import_trace
from memory_orchestrator.store import Store
from test_memory_trajectory import FIXTURE, trajectory_limits, indexed

before_hash = hashlib.sha256(Path('src/memory_orchestrator/evidence.py').read_bytes()).hexdigest()
ep = copy.deepcopy(FIXTURE['episode']); ep['events'] = ep['events'][:3]
control = 'USER_CONTROL_KEEP: keep only Q3 rows and never modify the original CSV.'
ep['events'][0]['text'] = (control + '\n<quoted_business_log>\n' + 'row,ok,0\n' * 1800
    + 'ERROR: this is quoted historical material\n' + 'row,ok,0\n' * 100 + '\n</quoted_business_log>')
idx = indexed(ep)
plan = evidence.build_trajectory_plan(idx, limits=trajectory_limits())
fragments = [f for p in plan['segments'] for f in p['fragments']
    if f['event_id'] == ep['events'][0]['event_id'] and f['structure']['namespace'] == 'event']
row = next(r for r in idx['records'].values() if r['source_event'] and r['event_id'] == ep['events'][0]['event_id'])
print('user_material', json.dumps({'role': evidence.learning_role(row),
    'provided_control': any(control in f['text'] for f in fragments),
    'provided_error': any('ERROR:' in f['text'] for f in fragments),
    'provided_starts': [f['range']['start_byte'] for f in fragments],
    'catalog_start_zero': any(c['ref_id'].startswith(row['base_ref'] + ':0:')
        for p in plan['segments'] for c in p['readable_ref_catalog']), 'coverage': plan['coverage']}))

with tempfile.TemporaryDirectory() as d:
    store = Store(Path(d) / 'store')
    ep = copy.deepcopy(FIXTURE['episode']); events = ep['events']; ep['events'] = []
    store.ensure_project(ep['project_id'])
    store.put('contexts', FIXTURE['context']['manifest_id'], FIXTURE['context'])
    src = Path(d) / 'source.jsonl'
    src.write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in events))
    caps = {'max_events': 200, 'max_bytes': 300000, 'max_event_bytes': 100000}
    ep = import_trace(store, ep, src, limits=caps)
    idx = evidence.index_episodes([ep], feedback=[FIXTURE['feedback']],
        contexts={FIXTURE['context']['manifest_id']: FIXTURE['context']}, store=store, trace_limits=caps)
    reader = idx['trace_readers'][0]; before = copy.deepcopy(reader.stats)
    plan = evidence.build_trajectory_plan(idx, limits=trajectory_limits(max_scan_events=3, max_segments=1))
    print('disk_scan', json.dumps({'before': before, 'after': reader.stats, 'coverage': plan['coverage']}))
print('source_unchanged', before_hash == hashlib.sha256(Path('src/memory_orchestrator/evidence.py').read_bytes()).hexdigest())
PY
```

实际退出码 `0`，`source_unchanged=true`。这里运行的是两项可证伪的构造边界 probe，不是“模型已学会提取”的证据，也没有重复跑完整测试代替逐输入检查。以上两项已直接发给根代理和 A，修复责任与后续验收由根代理安排。

## A 修复后的独立复测

在 A 结束 mutation 并确认恢复后，以同一完整命令原样复测（exit 0）。源码 hash 为 `5229d0ea1c6eed6a35ba5a4830685618282f1043601e9cd3c7e8aa04c51c0ca7`，运行前后未变：

```text
user_material: provided_control=true, provided_error=false, provided_starts=[0]
disk_scan: body_bytes=5813, range_reads=13, metadata_rows=450
coverage: scanned_events=3, scan_limit_scope=selection_events, raw_body_complete=false
source_unchanged=True
```

E01 已由相同反例关闭：用户控制前缀进入实际正文，quoted ERROR 不再抢首片段。E02 的**口径误认**已明确：选择扫描上限以 `scan_limit_scope=selection_events` 标注，plan 另暴露真实 read_stats；全量元数据遍历仍存在，不能将本次披露修正说成元数据读取也降到了 3 条。该成本限制作为已知边界保留，不因此扩展新的 I/O 框架。
