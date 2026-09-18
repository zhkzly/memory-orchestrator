"""Bounded independent B audit; synthetic model responses, real disk/Store flow."""
import copy
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

from memory_orchestrator.learning import learn
from memory_orchestrator.model import StructuredModel
from memory_orchestrator.schemas import DomainError
from memory_orchestrator.store import Store
from memory_orchestrator.trace import import_trace
from memory_orchestrator.sampling import sample_tasks
from test_memory_evidence import episode, event, csv_episodes, EXAMPLES
from test_memory_learning import policy, drafts
from test_memory_model import limits as model_limits, response

ROOT = Path(sys.argv[1]); ROOT.mkdir(parents=True, exist_ok=True)
summary = {'source_sha256': {}, 'probes': []}
for name in ('learning', 'evidence', 'goals', 'trace', 'maintenance', 'lineage'):
    file = Path('src/memory_orchestrator') / (name + '.py')
    summary['source_sha256'][str(file)] = hashlib.sha256(file.read_bytes()).hexdigest()

def field(request, label):
    return json.JSONDecoder().raw_decode(request['messages'][1]['content'].split(label, 1)[1].lstrip())[0]


# Actual disk trace, then derived missing-goal windows, then extraction transport.
store = Store(ROOT / 'trace-goals')
header = episode(); header['episode_id'] = 'disk-goals'; header['events'] = []
events = [event('u1', 'Inspect CSV parsing', 'instruction', source_role='user')]
events += [event('o' + str(i), 'observed Unicode 数据 ' * 180) for i in range(4)]
events += [event('u2', 'Switch to API auth', 'instruction', source_role='user')]
events += [event('m' + str(i), 'another observation 数据 ' * 180) for i in range(4)]
events += [event('u3', 'Return to CSV parsing', 'instruction', source_role='user'), event('done', 'Observed final result', 'result')]
raw = ROOT / 'raw-goals.jsonl'
raw.write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in events))
original_hash = hashlib.sha256(raw.read_bytes()).hexdigest()
index_limits = {'max_events': 4, 'max_bytes': 20000, 'max_event_bytes': 8000}
imported = import_trace(store, header, raw, limits=index_limits)
calls = []
def teacher(request):
    calls.append(copy.deepcopy(request))
    if request['prompt_id'] == 'extract_v1': return response(EXAMPLES['abstain'])
    assert request['prompt_id'] == 'goal_binding_v1'
    users = field(request, '用户事件正文：')
    caps = field(request, '本轮窗口和补读预算：')
    catalog = field(request, '已知或派生目标及依据：')
    ref = caps['target_user_refs'][0]
    target = next(e for e in users if e['ref_id'] == ref)
    if target['event_id'] == 'u1':
        assert 'Return to CSV' not in json.dumps(users)
        goal, revision, relation = 'new:csv', 'new:initial', 'continues'
    elif target['event_id'] == 'u2':
        goal, revision, relation = 'new:api', 'new:initial', 'switches'
    else:
        goal, revision, relation = catalog[0]['goal_id'], catalog[0]['revision'], 'resumes'
    return response({'status': 'completed', 'read_requests': [], 'reason': 'Constructed anchored association', 'unknowns': [],
        'bindings': [{'event_refs': [ref], 'anchor_user_ref': ref, 'goal_id': goal, 'revision': revision,
            'relation': relation, 'evidence_refs': [ref], 'reason': 'User explicitly names this task'}]})
settings = policy(trace_index=index_limits, dependency_lookup={'max_hops': 2, 'max_events': 4})
settings['goal_binding']['max_events'] = 1
model = StructuredModel(teacher, limits=model_limits(max_calls=6))
statuses = []
read_text = Path.read_text
def no_whole_trace(path, *args, **kwargs):
    if path.suffix in ('.jsonl', '.text'): raise AssertionError('Whole trace text load')
    return read_text(path, *args, **kwargs)
with patch.object(Path, 'read_text', no_whole_trace):
    for _ in range(8):
        result = learn(store, [imported['episode_id']], model, policy=settings)
        statuses.append(result['status'])
        if result['status'] != 'needs_index': break
        assert not calls
assert result['status'] == 'abstained', result
assert [c['prompt_id'] for c in calls] == ['goal_binding_v1'] * 3 + ['extract_v1']
packet = field(calls[-1], '证据包及缺口：')
assert packet['coverage']['total_event_count'] == len(events)
assert any(a['relation'] == 'resumes' and a['origin'] == 'model_proxy' for a in packet['goal_annotations'])
assert all(f['structure']['goal_id'] is None for f in packet['fragments'] if f['structure']['source_role'] == 'user')
assert store.get('episodes', imported['episode_id']) == imported
assert hashlib.sha256(raw.read_bytes()).hexdigest() == original_hash
summary['probes'].append({'kind': 'trace_to_learn_and_goal_windows', 'statuses': statuses,
    'calls': [c['prompt_id'] for c in calls], 'event_count': len(events), 'trace_ref': imported['trace_ref'],
    'read_stats': result['read_stats'], 'goal_annotations': packet['goal_annotations'], 'raw_unchanged': True})

# Hidden final parent is still forbidden even when dependency reading budget is zero.
store = Store(ROOT / 'frozen-parent')
parent = sample_tasks(store, [{'project_id': 'demo-project', 'task_id': 'heldout', 'revision': '1', 'description': 'Held out'}],
    lambda *args: {'artifact': 'PRIVATE HELDOUT RESULT'}, None,
    policy={'purpose': 'final', 'update_mode': 'none', 'repeat_count': 1, 'max_parallel': 1,
            'protocol_id': 'final-audit', 'executor': {'id': 'local', 'config': {}}},
    context_policy={'max_roots': 1, 'max_context_chars': 5000, 'relation_weight': 0})['episodes'][0]
header = episode(); header.update(episode_id='child-of-final', events=[])
raw = ROOT / 'child.jsonl'
raw.write_text(json.dumps(event('child', 'Parent-dependent result', parent_episode_id=parent['episode_id'], parent_event_id='result')) + '\n')
child = import_trace(store, header, raw, limits=index_limits)
calls = []
result = learn(store, [child['episode_id']], StructuredModel(lambda r: calls.append(r), limits=model_limits()),
    policy=policy(trace_index=index_limits, dependency_lookup={'max_hops': 0, 'max_events': 0}))
assert result['status'] == 'error' and result['errors'][0]['code'] == 'learning_not_permitted', result
assert calls == [] and store.list('experiences', 'demo-project') == []
summary['probes'].append({'kind': 'hidden_frozen_parent', 'status': result['status'],
    'error_code': result['errors'][0]['code'], 'model_calls': len(calls), 'experience_count': 0})

# Applied semantic maintenance affects the next real extraction request, not only a helper.
store = Store(ROOT / 'maintenance')
source = csv_episodes()
for ep in source: store.add_episode(ep)
ids = [ep['episode_id'] for ep in source]
extraction, diagnosis, _ = drafts(source)
old_draft = copy.deepcopy(extraction['experiences'][0])
old_draft['guidance']['steps'].append('Retain identifiers as strings')
old = {'record_id': 'prior-equivalent', 'project_id': 'demo-project', 'canonical_key': 'other-wording',
    'draft': old_draft, 'packet_id': 'original-packet', 'source_episode_ids': ids,
    'retained_evidence': [{'role': 'counterevidence_refs', 'ref_id': 'historical:boundary',
        'packet_id': 'original-packet', 'record_id': 'prior-equivalent', 'status': 'historical_reference_not_retracted'}],
    'created_at': '2026-09-18T00:00:00Z'}
store.put('experiences', old['record_id'], old)
first_calls = []
def maintenance_teacher(request):
    first_calls.append(copy.deepcopy(request))
    if request['prompt_id'] == 'extract_v1': return response(extraction)
    if request['prompt_id'] == 'maintain_experience_v1':
        fresh = field(request, '新经验：')
        pair = [fresh[0]['record_id'], old['record_id']]
        return response({'actions': [{'op': 'LINK_DUPLICATE', 'record_ids': pair,
            'preferred_record_id': pair[0], 'reason': 'Constructed scoped equivalence',
            'evidence_refs': ['experience:' + ref for ref in pair]}], 'unknowns': []})
    value = copy.deepcopy(diagnosis); value['necessity'].update(verdict='noop', allow_add=False)
    return response(value)
first = learn(store, ids, StructuredModel(maintenance_teacher, limits=model_limits(max_calls=6)), policy=policy())
assert first['status'] == 'noop', first
second_calls = []
def later(request):
    second_calls.append(copy.deepcopy(request)); return response(EXAMPLES['abstain'])
second = learn(store, ids, StructuredModel(later, limits=model_limits(max_calls=2)), policy=policy())
assert second['status'] == 'abstained' and len(second_calls) == 1, second
related = field(second_calls[0], '相关经历/反例：')
assert len(related) == 1, related
assert set(related[0]['maintenance_member_ids']) == {old['record_id'], first['experience_ids'][0]}
assert 'historical:boundary' in json.dumps(related)
assert store.get('experiences', old['record_id']) == old
summary['probes'].append({'kind': 'semantic_maintenance_to_next_learn',
    'first_prompts': [c['prompt_id'] for c in first_calls], 'second_prompts': [c['prompt_id'] for c in second_calls],
    'related_count': len(related), 'member_ids': related[0]['maintenance_member_ids'],
    'retained_boundary': 'historical:boundary', 'raw_experience_unchanged': True})
summary['status'] = 'all_probes_passed'
(ROOT / 'results.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
print(json.dumps({'status': summary['status'], 'probes': summary['probes'], 'path': str(ROOT / 'results.json')}, ensure_ascii=False))
