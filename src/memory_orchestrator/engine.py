"""One explicit evolution cycle; callers supply execution, not release decisions."""
from .evaluation import compare_candidates
from .learning import learn
from .release import publish
from .schemas import DomainError, new_id


def evolve(store, episode_ids, model, *, learning_policy, case_set, protocol,
           execute, evaluate, max_parallel):
    """Learn, compare and publish exactly the selected accepted candidate.

    Use learn() alone when evaluation inputs are not available. This function
    performs no native Agent integration, autonomous polling or background work.
    """
    learning = learn(store, episode_ids, model, policy=learning_policy)
    result = {'learning': learning, 'comparison': None, 'release': None, 'status': learning['status']}
    if not learning['candidate_ids']:
        return result
    candidates = [store.get('candidates', identifier) for identifier in learning['candidate_ids']]
    project = candidates[0]['project_id']
    stage = 'compare'
    try:
        comparison = compare_candidates(store, project, candidates, case_set, protocol,
                                        execute, evaluate, max_parallel=max_parallel)
        result['comparison'] = comparison
        selection = store.get('selections', comparison['selection_id'])
        if selection['decision'] != 'selected':
            result['status'] = 'not_selected'
            return result
        selected = next(c for c in candidates if c['candidate_digest'] == selection['selected_candidate_digest'])
        stage = 'publish'
        result['release'] = publish(store, project, selected['proposal_id'], selection['selected_validation_ref'],
                                    selection['selection_id'], expected_active_digest=selection['base_digest'],
                                    expected_generation=selection['expected_generation'])
        result['status'] = 'published'
        return result
    except DomainError as exc:
        error_id = new_id('evolution_error')
        store.put('errors', error_id, {'error_id': error_id, 'project_id': project,
                  'cycle_id': learning['cycle_id'], 'stage': stage, 'code': exc.code,
                  'message': exc.message, 'details': exc.details, 'comparison': result['comparison']})
        result.update(status='error', error_id=error_id)
        return result
