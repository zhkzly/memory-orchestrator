"""One explicit evolution cycle; callers supply execution, not release decisions."""
from .evaluation import capture_rejected_target_episodes, compare_candidates
from .learning import learn
from .release import publish
from .schemas import DomainError, new_id


def evolve(store, episode_ids, model, *, learning_policy, case_set, protocol,
           execute, evaluate, max_parallel, verification=None, execute_view=None, asset_runner=None):
    """Learn, compare and publish exactly the selected accepted candidate.

    Use learn() alone when evaluation inputs are not available. This function
    performs no native Agent integration, autonomous polling or background work.
    """
    from .verification import verification_catalog
    learning = learn(store, episode_ids, model, policy=learning_policy,
                     verification_catalog=verification_catalog(case_set,verification))
    result = {'learning': learning, 'comparison': None, 'release': None,
              'next_episode_ids': [], 'status': learning['status']}
    if not learning['candidate_ids']:
        return result
    candidates = [store.get('candidates', identifier) for identifier in learning['candidate_ids']]
    project = candidates[0]['project_id']
    stage = 'compare'
    try:
        comparison = compare_candidates(store, project, candidates, case_set, protocol,
                                        execute, evaluate, max_parallel=max_parallel,
                                        verification=verification, execute_view=execute_view,asset_runner=asset_runner)
        result['comparison'] = comparison
        if comparison.get('status')=='blocked':
            result['status']='blocked';return result
        selection = store.get('selections', comparison['selection_id'])
        if selection['decision'] != 'selected':
            stage = 'rejection_handoff'
            result['next_episode_ids'] = capture_rejected_target_episodes(store, comparison)
            result['status'] = 'not_selected'
            return result
        selected_entry = next(entry for entry in selection['candidate_validations']
                              if entry['candidate_digest'] == selection['selected_candidate_digest'])
        selected_id = selected_entry['proposal_ids'][0]
        selected = store.get('candidates', selected_id)
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
