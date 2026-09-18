"""Shared execution termination and artifact-evaluation policy, without I/O."""
from .schemas import DomainError, json_bytes


TERMINAL_STATUSES = ('completed', 'cancelled', 'timeout', 'budget_exhausted', 'adapter_error')
SCORING_POLICIES = ('completed_only', 'available_artifact')


def resolve_scoring_policy(value, *, default):
    selected = default if value is None else value
    if selected not in SCORING_POLICIES:
        raise DomainError('scoring_policy', 'Use completed_only or available_artifact explicitly.')
    return selected


def parse_execution(output, error, policy):
    """Describe termination independently of task success.

    ``error`` is a real invocation/identity/format error, not merely a normally
    returned timeout/cancellation. Presence of artifact (including explicit null)
    means the independent evaluator can judge it under available_artifact.
    """
    policy = resolve_scoring_policy(policy, default=None)
    has_artifact = isinstance(output, dict) and 'artifact' in output
    if error is not None:
        kind = error.get('type') if isinstance(error, dict) else type(error).__name__
        code = error.get('code') if isinstance(error, dict) else None
        status = ('cancelled' if kind == 'CancelledError' or code == 'cancelled' else
                  'timeout' if kind in ('TimeoutError', 'APITimeoutError') or code == 'timeout' else
                  'budget_exhausted' if code == 'budget_exhausted' else 'adapter_error')
        return {'execution_status': status, 'eligible': False, 'has_artifact': has_artifact,
                'reason': 'Invocation, identity or format error prevents evaluation.'}
    if not isinstance(output, dict):
        return {'execution_status': 'adapter_error', 'eligible': False, 'has_artifact': False,
                'reason': 'Execution must return a JSON object.'}
    try:
        json_bytes(output)
    except DomainError:
        return {'execution_status': 'adapter_error', 'eligible': False, 'has_artifact': has_artifact,
                'reason': 'Execution output is not finite JSON.'}
    status = output.get('execution_status', 'completed')
    if status not in TERMINAL_STATUSES:
        return {'execution_status': 'adapter_error', 'eligible': False, 'has_artifact': has_artifact,
                'reason': 'Execution returned an unsupported terminal status.'}
    if status == 'adapter_error':
        return {'execution_status': status, 'eligible': False, 'has_artifact': has_artifact,
                'reason': 'An adapter error cannot provide bound evaluation material.'}
    if not has_artifact:
        return {'execution_status': 'adapter_error' if status == 'completed' else status,
                'eligible': False, 'has_artifact': False, 'reason': 'No artifact was returned.'}
    allowed = status == 'completed' or policy == 'available_artifact'
    return {'execution_status': status, 'eligible': allowed, 'has_artifact': True,
            'reason': None if allowed else 'The recorded completed_only policy does not evaluate this terminal state.'}
