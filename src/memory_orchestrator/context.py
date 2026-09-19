"""N02: pin a library, then disclose whole dependency groups within a budget."""
from __future__ import annotations

import json
import math
import re

from .schemas import DomainError, digest, new_id, validate
from .telemetry import measure_stage


def terms(text):
    """Small lexical retrieval heuristic, not a semantic applicability proof."""
    stop = {'a', 'an', 'the', 'and', 'or', 'to', 'of', 'for', 'in', 'with', 'is', 'be', 'must'}
    result = set(re.findall(r'[a-z0-9_]+', text.casefold())) - stop
    for phrase in re.findall(r'[\u4e00-\u9fff]+', text):
        result.update(phrase[i:i + 2] for i in range(max(1, len(phrase) - 1)))
    return result


def _scope_phrases(text, phrases):
    """Return explicit machine scope phrases found in public task text."""
    normalized = ' '.join(text.casefold().split())
    return sorted(phrase for phrase in phrases
                  if ' '.join(phrase.casefold().split()) in normalized)


def select_context(store, task, policy, *, explicit_snapshot=None, purpose='learning'):
    with measure_stage(store, task['project_id'], 'select', purpose=purpose,
                       subject_ref=task.get('task_id')):
        return _select_context(store, task, policy, explicit_snapshot=explicit_snapshot)


def _fact_score(fact, task, query):
    declared = fact.get('applicability')
    if declared is not None:
        if declared.get('global') is True:
            return 1.0, 'declared_global'
        if declared.get('task_ids') and task.get('task_id') not in declared['task_ids']:
            return None, 'task_relevance'
        if declared.get('task_families') and task.get('task_family') not in declared['task_families']:
            return None, 'task_relevance'
        keywords = terms(' '.join(declared.get('query_terms', [])))
        if keywords and not keywords & query:
            return None, 'task_relevance'
        if not any(declared.get(key) for key in ('task_ids', 'task_families', 'query_terms')):
            overlap = len(query & terms(fact['content']))
            return (float(overlap), 'lexical_task_overlap') if overlap else (None, 'task_relevance')
        return 1.0 + len(query & terms(fact['content'])), 'declared_applicability'
    # Legacy global user preferences remain usable; new scoped facts can declare applicability.
    if fact['kind'] == 'user':
        return 1.0 + len(query & terms(fact['content'])), 'legacy_user_unspecified_applicability'
    overlap = len(query & terms(fact['content']))
    return (float(overlap), 'lexical_task_overlap') if overlap else (None, 'task_relevance')


def relation_applicability(store, relation, task, snapshot):
    """Check the measured/observed scope without upgrading it to causal truth."""
    if relation.get('project_id') != task['project_id'] or relation.get('kind') not in ('co_used', 'measured_effect'):
        return False, 'relation_kind_or_project'
    if not relation.get('supporting_refs') or type(relation.get('value')) not in (int, float) or not math.isfinite(relation['value']):
        return False, 'relation_evidence'
    scope = relation.get('applicable_context')
    if isinstance(scope, str):
        if scope != task.get('task_id'):
            return False, 'task_scope'
    elif isinstance(scope, dict):
        if scope.get('task_family') is not None and scope['task_family'] != task.get('task_family'):
            return False, 'task_family'
        if scope.get('task_ids') and task.get('task_id') not in scope['task_ids']:
            return False, 'task_scope'
        if not scope.get('task_family') and not scope.get('task_ids'):
            return False, 'unknown_scope'
    else:
        return False, 'unknown_scope'
    try:
        source = store.snapshot(relation.get('source_snapshot_digest') or relation.get('snapshot_digest'))
        if source['project_id'] != task['project_id']:
            return False, 'source_project'
        pair = (relation['from'], relation['to'])
        if any(key not in source['skills'] for key in pair):
            return False, 'source_skill'
        revisions = relation.get('skill_revisions')
        if relation['kind'] == 'measured_effect':
            validate('MeasuredEffect', relation)
            plan = store.get('contrast_plans', relation['contrast_plan_ref'])
            if plan['source_snapshot_digest'] != source['snapshot_id'] or any(plan[key] != relation[key] for key in ('from', 'to')):
                return False, 'contrast_binding'
            witnesses = [r for r in store.list('contrast_results', project_id=task['project_id'])
                         if r.get('plan_ref') == plan['contrast_plan_id'] and r.get('plan_hash') == digest(plan)
                         and r.get('relation_ref') == relation['relation_id'] and r.get('value') == relation['value']]
            if len(witnesses) != 1:
                return False, 'contrast_evidence'
        if revisions is None:
            revisions = {key: source['skills'][key]['revision'] for key in pair}
        checks = dict(revisions)
        checks.update(relation.get('dependency_revisions', {}))
        checks.update({r['skill_id']: r['revision'] for r in relation.get('background_skill_refs', [])})
        if any(key not in snapshot['skills'] or snapshot['skills'][key]['revision'] != revision
               or key not in source['skills'] or source['skills'][key]['revision'] != revision for key, revision in checks.items()):
            return False, 'skill_revision'
        if source['snapshot_id'] != snapshot['snapshot_id']:
            committed = store.release_history(task['project_id'])
            published = {row['new_digest'] for row in committed} | {row['expected_active_digest'] for row in committed}
            published.add(store.active(task['project_id'])['snapshot_id'])
            if source['snapshot_id'] not in published:
                return False, 'unpublished_source'
    except (DomainError, KeyError, TypeError):
        return False, 'unverifiable_relation'
    return True, 'matching_scope_and_revisions'


def _select_context(store, task, policy, *, explicit_snapshot=None):
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
    fact_refs, fact_selection, ranked_facts = [], [], []
    query = terms(task['description'])
    for fact in facts['user'] + facts['project']:
        score, reason = _fact_score(fact, task, query)
        if score is None:
            exclusions.append({'memory_id': fact['memory_id'], 'record_id': fact['record_id'], 'reason': reason})
            continue
        ranked_facts.append((score, fact['record_id'], fact, reason))
    for score, _, fact, reason in sorted(ranked_facts, key=lambda row: (-row[0], row[1])):
        text = fact['content']
        cost = len(text) + (1 if chunks else 0)
        if used + cost <= budget:
            chunks.append(text)
            used += cost
            fact_refs.append(fact['record_id'])
            fact_selection.append({'record_id': fact['record_id'], 'score': score, 'reason': reason})
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

    requested_family = terms(task.get('task_family') or '')
    scores = {}
    for sid, skill in skills.items():
        content = skill['content']
        selector = content['scope'].get('retrieval')
        if selector is not None:
            excluded = _scope_phrases(task['description'], selector['exclude_any'])
            if excluded:
                exclusions.append({'skill_id': sid, 'reason': 'scope_exclusion',
                                   'matched_terms': excluded})
                continue
            required = _scope_phrases(task['description'], selector['require_any'])
            if not required:
                exclusions.append({'skill_id': sid, 'reason': 'scope_requirement'})
                continue
        else:
            required = []
        family_match = len((requested_family or query) & terms(content['scope']['task_family']))
        trigger_matches = len(query & terms(' '.join(content['triggers'])))
        if not (family_match or trigger_matches or required):
            exclusions.append({'skill_id': sid, 'reason': 'scope_or_trigger'})
        else:
            scores[sid] = float(trigger_matches + family_match + 2 * len(required))
    relations, relation_filters = [], []
    for relation in store.list('relations', project_id=project):
        eligible, reason = relation_applicability(store, relation, task, snapshot)
        relation_filters.append({'relation_id': relation['relation_id'], 'eligible': eligible, 'reason': reason})
        if eligible:
            relations.append(relation)

    def score(sid):
        related, references = 0.0, []
        for relation in relations:
            forward = relation.get('from') == sid and relation.get('to') in selected
            reverse_co_use = relation.get('kind') == 'co_used' and relation.get('to') == sid and relation.get('from') in selected
            if not (forward or reverse_co_use):
                continue
            needed_background = {r['skill_id'] for r in relation.get('background_skill_refs', [])}
            if not needed_background <= set(selected) | set(closure(sid)):
                continue
            value = relation.get('value')
            if relation.get('kind') in ('co_used', 'measured_effect') and relation.get('supporting_refs'):
                if type(value) in (int, float) and math.isfinite(value):
                    related += value
                    references.append(relation['relation_id'])
        return scores[sid] + weight * related, references

    while scores and len(roots) < policy['max_roots']:
        sid = min(scores, key=lambda s: (-score(s)[0], s))
        ranking, relation_refs = score(sid)
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
        roots.append({'skill_id': sid, 'score': ranking, 'relation_refs': relation_refs})
    exclusions.extend({'skill_id': sid, 'reason': 'root_limit'} for sid in scores if sid not in selected)
    supplied = '\n'.join(chunks)
    manifest = {'manifest_id': new_id('context'), 'project_id': project,
                'task_ref': task.get('task_id'), 'task_revision': task.get('revision'),
                'snapshot_digest': snapshot['snapshot_id'],
                'selected_skills': [{'skill_id': s, 'revision': skills[s]['revision']} for s in selected],
                'dependency_closure': selected, 'roots': roots, 'supplied_text': supplied,
                'supplied_hash': digest(supplied), 'exclusions': exclusions,
                'fact_refs': fact_refs, 'fact_read_errors': facts['errors'], 'fact_selection': fact_selection,
                'relation_filters': relation_filters,
                'selection_method': 'explicit scope retrieval phrases when present, then lexical family/trigger ranking; prose conditions remain advisory',
                'budget': {'unit': 'characters', 'limit': budget, 'used': len(supplied),
                           'token_measurement': 'not_measured'},
                'consumption_observability': 'unknown'}
    store.put('contexts', manifest['manifest_id'], manifest)
    return manifest
