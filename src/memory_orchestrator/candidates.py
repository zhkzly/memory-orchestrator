"""N08: apply a bounded patch to one immutable base; never change active."""
from copy import deepcopy
from pathlib import PurePosixPath

from .schemas import DomainError, digest, new_id, validate


def skill_view(snapshot):
    """Rule IDs are scoped to the explicit revision, not mutable list indices."""
    return {sid: {**deepcopy(skill), 'rules': [{'rule_id': f'R{i + 1}', 'text': text}
                                             for i, text in enumerate(skill['content']['steps'])]}
            for sid, skill in snapshot['skills'].items()}


def _references(value, allowed):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ('evidence_refs', 'supporting_refs', 'counterevidence_refs', 'boundary_refs'):
                unknown = set(item) - allowed
                if unknown:
                    raise DomainError('unsupported_evidence', 'Patch cites evidence not provided to its author',
                                      {'field': key, 'unknown_refs': sorted(unknown)})
            else:
                _references(item, allowed)
    elif isinstance(value, list):
        for item in value:
            _references(item, allowed)


def _path(path):
    parsed = PurePosixPath(path)
    if (parsed.is_absolute() or str(parsed) != path or len(parsed.parts) < 2
            or parsed.parts[0] not in ('scripts', 'references', 'templates')
            or any(part in ('', '.', '..') for part in parsed.parts) or '\\' in path
            or any(ord(ch) < 32 for ch in path)):
        raise DomainError('asset_path', 'Asset path must be normalized and remain inside its owner', {'path': path})
    return path


def _require_scope_selector(content):
    selector = content.get('scope', {}).get('retrieval')
    if not isinstance(selector, dict) or not selector.get('require_any'):
        raise DomainError('scope_selector',
                          'A new Skill needs explicit scope.retrieval.require_any and exclude_any task-text phrases.')


def _edit_skill(skill, edits):
    rows = [(f'R{i + 1}', value) for i, value in enumerate(skill['content']['steps'])]
    original = {key for key, _ in rows}
    modified = set()
    for index, edit in enumerate(edits):
        kind = edit['kind']
        if kind == 'SET_FIELD':
            field = edit['field']
            if field in modified:
                raise DomainError('duplicate_edit', f'Multiple assignments to {field}')
            modified.add(field)
            skill['content'][field] = deepcopy(edit['value'])
            continue
        key = edit.get('rule_id', edit.get('after_rule_id'))
        if key is not None and key not in original:
            raise DomainError('rule_ref', 'Rule ID must come from the provided base revision', {'rule_id': key})
        positions = [i for i, (row_key, _) in enumerate(rows) if row_key == key]
        if key is not None and not positions:
            raise DomainError('rule_ref', 'Rule was already removed', {'rule_id': key})
        if kind != 'ADD_RULE' and key in modified:
            raise DomainError('duplicate_edit', 'Rule was already edited', {'rule_id': key})
        if kind == 'ADD_RULE':
            at = len(rows) if key is None else positions[0] + 1
            rows.insert(at, (f'new_rule_{index}', edit['text']))
        elif kind == 'REPLACE_RULE':
            rows[positions[0]] = (key, edit['text'])
            modified.add(key)
        elif kind == 'REMOVE_RULE':
            rows.pop(positions[0])
            modified.add(key)
    skill['content']['steps'] = [value for _, value in rows]


def apply_candidate(store, project_id, patch, *, base_digest, expected_generation,
                    allowed_evidence_refs, allowed_skill_ids, max_operations, max_skills, max_asset_bytes,
                    diagnosis_ref=None, diagnosis_hash=None):
    """Return a persisted proposal or None for NOOP/unchanged content.

    Allowed evidence is the caller's verified supplied-reference set. This tests
    availability, not whether natural-language causal claims are true.
    """
    patch = validate('PatchDraft', patch)
    for name, value in [('max_operations', max_operations), ('max_skills', max_skills),
                        ('max_asset_bytes', max_asset_bytes), ('expected_generation', expected_generation)]:
        if type(value) is not int or value < 0:
            raise DomainError('patch_budget', f'{name} must be an explicit nonnegative integer')
    active = store.active(project_id)
    if active['snapshot_id'] != base_digest or active['generation'] != expected_generation:
        raise DomainError('stale_base', 'Proposal base/generation no longer matches active')
    base = store.snapshot(base_digest)
    if base['project_id'] != project_id:
        raise DomainError('project_mismatch', 'Candidate base belongs to another project')
    if (diagnosis_ref is None) != (diagnosis_hash is None):
        raise DomainError('diagnosis_binding', 'Diagnosis reference and hash must be supplied together')
    if diagnosis_ref is not None:
        diagnosis = store.get('diagnoses', diagnosis_ref)
        if (diagnosis.get('project_id') != project_id or diagnosis.get('base_digest') != base_digest
                or digest(diagnosis) != diagnosis_hash):
            raise DomainError('diagnosis_binding', 'Diagnosis does not match this project/base/content')
    _references(patch, set(allowed_evidence_refs))
    if patch['operations'][0]['op'] == 'NOOP':
        return None
    atomic_count = sum(len(op['edits']) if op['op'] == 'PATCH' else 1 for op in patch['operations']) + len(patch['asset_edits'])
    if atomic_count > max_operations:
        raise DomainError('patch_budget', 'Atomic operation limit exceeded', {'actual': atomic_count, 'limit': max_operations})
    skills, assets = deepcopy(base['skills']), deepcopy(base['assets'])
    allowed = set(allowed_skill_ids)
    if not allowed.issubset(skills):
        raise DomainError('target_ref', 'Allowed targets contain absent Skills')
    names, targets, changed, replacements = {}, set(), set(), []
    for operation in patch['operations']:
        if operation['op'] == 'ADD':
            local = 'new:' + operation['proposed_slug']
            if local in names:
                raise DomainError('duplicate_skill', 'ADD names must be unique in a proposal')
            names[local] = 'skill_' + digest([project_id, base_digest, operation['proposed_slug'], patch])[:24]
        else:
            target = operation['target_skill_id']
            if target in targets or target not in allowed:
                raise DomainError('target_scope', 'Repeated or unauthorized edit target', {'skill_id': target})
            targets.add(target)
            if skills[target]['revision'] != operation['expected_revision']:
                raise DomainError('stale_revision', 'Expected Skill revision does not match base', {'skill_id': target})

    def resolve(ref):
        if ref.startswith('new:'):
            if ref not in names:
                raise DomainError('new_skill_ref', 'Reference to undeclared ADD', {'ref': ref})
            return names[ref]
        return ref

    for operation in patch['operations']:
        kind = operation['op']
        if kind == 'ADD':
            sid = names['new:' + operation['proposed_slug']]
            skills[sid] = {'skill_id': sid, 'project_id': project_id, 'revision': 'pending',
                           'content': deepcopy(operation['content']), 'asset_refs': []}
            changed.add(sid)
        elif kind == 'PATCH':
            sid = operation['target_skill_id']
            _edit_skill(skills[sid], operation['edits'])
            changed.add(sid)
        elif kind == 'RETIRE':
            sid = operation['target_skill_id']
            if operation['replacement_skill_id'] is not None:
                replacements.append(resolve(operation['replacement_skill_id']))
            for ref in skills[sid]['asset_refs']:
                del assets[ref]
            del skills[sid]
            changed.add(sid)
    for sid in changed & skills.keys():
        for field in ('depends_on', 'declared_conflicts'):
            skills[sid]['content'][field] = [resolve(x) for x in skills[sid]['content'][field]]
    if any(ref not in skills for ref in replacements):
        raise DomainError('replacement_ref', 'Retirement replacement must survive the proposal')
    seen_assets = set()
    for edit in patch['asset_edits']:
        sid = resolve(edit['owner_skill_ref'])
        if sid not in skills or sid not in allowed | set(names.values()):
            raise DomainError('asset_owner', 'Asset owner is outside the allowed edit scope')
        path = sid + '/' + _path(edit['relative_path'])
        if path in seen_assets:
            raise DomainError('duplicate_asset_edit', 'Asset edited twice in one proposal')
        seen_assets.add(path)
        current_hash = digest(assets[path]) if path in assets else None
        if current_hash != edit['expected_hash']:
            raise DomainError('stale_asset', 'Asset precondition differs from base', {'path': path})
        if edit['op'] == 'UPSERT':
            assets[path] = edit['content']
        else:
            del assets[path]
        changed.add(sid)
    if len(skills) > max_skills or sum(len(value.encode('utf-8')) for value in assets.values()) > max_asset_bytes:
        raise DomainError('library_budget', 'Complete candidate library exceeds the explicit asset/Skill budget')
    for sid in changed & skills.keys():
        skill = skills[sid]
        skill['content'] = validate('SkillContent', skill['content'])
        old = base['skills'].get(sid)
        if old is None or skill['content'].get('scope') != old['content'].get('scope'):
            _require_scope_selector(skill['content'])
        skill['asset_refs'] = sorted(path for path in assets if path.startswith(sid + '/'))
        # An unchanged PATCH cannot create a new version solely by changing its revision string.
        material = {'content': skill['content'], 'assets': {key: assets[key] for key in skill['asset_refs']}}
        old_material = None if old is None else {'content': old['content'], 'assets': {key: base['assets'][key] for key in old['asset_refs']}}
        skill['revision'] = old['revision'] if material == old_material else digest(material)
    if skills == base['skills'] and assets == base['assets']:
        return None
    snapshot = store.save_snapshot(project_id, skills, assets, parent=base_digest)
    proposal = {'proposal_id': new_id('proposal'), 'project_id': project_id, 'base_digest': base_digest,
                'candidate_digest': snapshot['snapshot_id'], 'expected_generation': expected_generation,
                'patch': patch, 'changed_skill_refs': sorted(changed),
                'coupled_asset_hashes': {key: digest(value) for key, value in assets.items()},
                'evidence_refs': patch['evidence_refs'], 'expected_behavior': patch['expected_behavior'],
                'check_plan': patch['check_plan'], 'skill_aliases': names,
                'diagnosis_ref': diagnosis_ref, 'diagnosis_hash': diagnosis_hash}
    store.put('candidates', proposal['proposal_id'], proposal)
    return proposal
