"""N02: pin a library, then disclose whole dependency groups within a budget."""
from __future__ import annotations

import json
import math
import re

from .schemas import DomainError, digest, new_id


def terms(text):
    """Small lexical retrieval heuristic, not a semantic applicability proof."""
    stop = {'a', 'an', 'the', 'and', 'or', 'to', 'of', 'for', 'in', 'with', 'is', 'be', 'must'}
    result = set(re.findall(r'[a-z0-9_]+', text.casefold())) - stop
    for phrase in re.findall(r'[\u4e00-\u9fff]+', text):
        result.update(phrase[i:i + 2] for i in range(max(1, len(phrase) - 1)))
    return result


def select_context(store, task, policy, *, explicit_snapshot=None):
    """Select by task family/trigger text; prose conditions remain advisory.

    Budget units are Unicode characters, not a claim about model tokenization.
    An explicit snapshot is intended for isolated candidate comparisons.
    """
    project = task['project_id']
    for name in ('max_roots', 'max_context_chars'):
        if type(policy.get(name)) is not int or policy[name] < 0:
            raise DomainError('context_policy', f'{name} must be an explicit nonnegative integer')
    weight = policy.get('relation_weight')
    if type(weight) not in (int, float) or not math.isfinite(weight) or weight < 0:
        raise DomainError('context_policy', 'relation_weight must be explicit, finite and nonnegative')
    active = store.ensure_project(project)
    snapshot = store.snapshot(explicit_snapshot or active['snapshot_id'])
    if snapshot['project_id'] != project:
        raise DomainError('project_mismatch', 'Selected snapshot belongs to another project')
    skills = snapshot['skills']
    selected, exclusions, chunks, roots = [], [], [], []
    budget = policy['max_context_chars']
    used = 0
    facts = store.facts(project)
    fact_refs = []
    for fact in facts['user'] + facts['project']:
        text = fact['content']
        cost = len(text) + (1 if chunks else 0)
        if used + cost <= budget:
            chunks.append(text)
            used += cost
            fact_refs.append(fact['record_id'])
        else:
            exclusions.append({'memory_id': fact['memory_id'], 'reason': 'budget'})

    def closure(root, visiting=None):
        visiting = set() if visiting is None else visiting
        if root in visiting or root not in skills:
            raise DomainError('dependency', f'Missing or cyclic dependency: {root}')
        visiting.add(root)
        result = []
        for dependency in skills[root]['content']['depends_on']:
            for item in closure(dependency, visiting):
                if item not in result:
                    result.append(item)
        visiting.remove(root)
        if root not in result:
            result.append(root)
        return result

    def conflicts(ids):
        values = set(ids)
        return any(values.intersection(skills[s]['content']['declared_conflicts']) for s in values)

    query = terms(task['description'])
    requested_family = terms(task.get('task_family') or '')
    scores = {}
    for sid, skill in skills.items():
        content = skill['content']
        family_match = len((requested_family or query) & terms(content['scope']['task_family']))
        trigger_matches = len(query & terms(' '.join(content['triggers'])))
        if not (family_match or trigger_matches):
            exclusions.append({'skill_id': sid, 'reason': 'scope_or_trigger'})
        else:
            scores[sid] = float(trigger_matches + family_match)
    relations = store.list('relations', project_id=project)

    def score(sid):
        related = 0.0
        for relation in relations:
            forward = relation.get('from') == sid and relation.get('to') in selected
            reverse_co_use = relation.get('kind') == 'co_used' and relation.get('to') == sid and relation.get('from') in selected
            if not (forward or reverse_co_use):
                continue
            value = relation.get('value')
            if relation.get('kind') in ('co_used', 'measured_effect') and relation.get('supporting_refs'):
                if type(value) in (int, float) and math.isfinite(value):
                    related += value
        return scores[sid] + weight * related

    while scores and len(roots) < policy['max_roots']:
        sid = min(scores, key=lambda s: (-score(s), s))
        ranking = score(sid)
        del scores[sid]
        if sid in selected:
            continue
        group = closure(sid)
        if conflicts(selected + group):
            exclusions.append({'skill_id': sid, 'reason': 'declared_conflict'})
            continue
        additional = [item for item in group if item not in selected]
        disclosures = []
        for item in additional:
            skill = skills[item]
            payload = {'skill_id': item, 'revision': skill['revision'], 'content': skill['content'],
                       'asset_catalog': [{'path': ref, 'hash': digest(snapshot['assets'][ref])}
                                         for ref in skill['asset_refs']]}
            disclosures.append(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        cost = sum(map(len, disclosures)) + max(0, len(disclosures) - 1) + int(bool(chunks and disclosures))
        if used + cost > budget:
            exclusions.append({'skill_id': sid, 'reason': 'budget'})
            continue
        selected.extend(additional)
        chunks.extend(disclosures)
        used += cost
        roots.append({'skill_id': sid, 'score': ranking})
    exclusions.extend({'skill_id': sid, 'reason': 'root_limit'} for sid in scores if sid not in selected)
    supplied = '\n'.join(chunks)
    manifest = {'manifest_id': new_id('context'), 'project_id': project,
                'task_ref': task.get('task_id'), 'task_revision': task.get('revision'),
                'snapshot_digest': snapshot['snapshot_id'],
                'selected_skills': [{'skill_id': s, 'revision': skills[s]['revision']} for s in selected],
                'dependency_closure': selected, 'roots': roots, 'supplied_text': supplied,
                'supplied_hash': digest(supplied), 'exclusions': exclusions,
                'fact_refs': fact_refs, 'fact_read_errors': facts['errors'],
                'selection_method': 'lexical family/trigger overlap; prose conditions remain advisory',
                'budget': {'unit': 'characters', 'limit': budget, 'used': len(supplied),
                           'token_measurement': 'not_measured'},
                'consumption_observability': 'unknown'}
    store.put('contexts', manifest['manifest_id'], manifest)
    return manifest
