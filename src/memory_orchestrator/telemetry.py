"""Measured local maintenance work; provider calls retain their own usage ledger."""
from contextlib import contextmanager
import math
import time

from .schemas import DomainError, new_id, now_iso


STAGES = {'prepare', 'select', 'index', 'execute', 'evaluate', 'extract', 'diagnose',
          'propose', 'validate_overhead', 'publish', 'recover', 'report'}


class StageMeter:
    def __init__(self):
        self.delegated = 0.0
        self.measurement_id = new_id('stage')

    def exclude(self, seconds):
        """Exclude measured synchronous work already charged by another record."""
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
            raise DomainError('stage_measurement', 'Delegated time must be finite and nonnegative.')
        self.delegated += seconds


@contextmanager
def measure_stage(store, project_id, stage, *, purpose='learning', subject_ref=None,
                  price_per_second=None, currency=None):
    if stage not in STAGES or purpose not in ('learning', 'validation', 'final', 'maintenance'):
        raise DomainError('stage_measurement', 'Use a declared stage and purpose.')
    if price_per_second is not None and (type(price_per_second) not in (int, float)
            or not math.isfinite(price_per_second) or price_per_second < 0
            or not isinstance(currency, str) or not currency.strip()):
        raise DomainError('stage_price', 'A declared nonnegative rate requires a currency.')
    if price_per_second is None and currency is not None:
        raise DomainError('stage_price', 'Currency without a rate is not a price.')
    meter, started_at, started = StageMeter(), now_iso(), time.monotonic()
    error = None
    try:
        yield meter
    except BaseException as exc:
        error = exc
    elapsed = time.monotonic() - started
    local = elapsed - meter.delegated
    gaps = []
    if local < -1e-6:
        local = None
        gaps.append('Excluded time exceeds the observed interval; local time and cost are unknown.')
    elif local is not None:
        local = max(0.0, local)
    record = {'measurement_id': meter.measurement_id, 'project_id': project_id, 'stage': stage,
              'purpose': purpose, 'subject_ref': subject_ref, 'started_at': started_at,
              'finished_at': now_iso(), 'elapsed_seconds': elapsed, 'delegated_seconds': meter.delegated,
              'local_seconds': local, 'status': 'error' if error else 'ok',
              'error_code': getattr(error, 'code', type(error).__name__) if error else None,
              'monetary_cost': local * price_per_second if local is not None and price_per_second is not None else None,
              'currency': currency, 'price_per_second': price_per_second, 'gaps': gaps}
    try:
        store.put('stage_measurements', record['measurement_id'], record)
    except Exception as storage_error:
        if error is not None:
            error.add_note('Stage measurement persistence also failed: ' + type(storage_error).__name__)
            raise error from storage_error
        raise
    if error is not None:
        raise error


def summarize_stages(records):
    by_stage, costs, unique = {}, {}, {}
    for row in records:
        identifier = row['measurement_id']
        if identifier in unique and unique[identifier] != row:
            raise DomainError('stage_measurement', 'One measurement ID has conflicting contents.')
        unique[identifier] = row
    for row in unique.values():
        bucket = by_stage.setdefault(row['stage'], {'measurements': 0, 'local_seconds': 0.0,
            'missing_time_measurements': 0, 'unpriced_measurements': 0, 'errors': 0})
        bucket['measurements'] += 1
        bucket['errors'] += row['status'] == 'error'
        seconds = row['local_seconds']
        if seconds is None:
            bucket['missing_time_measurements'] += 1
        elif type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
            raise DomainError('stage_measurement', 'Invalid observed maintenance time.')
        else:
            bucket['local_seconds'] += seconds
        cost, currency = row['monetary_cost'], row['currency']
        if cost is None or currency is None:
            bucket['unpriced_measurements'] += 1
        elif type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0:
            raise DomainError('stage_measurement', 'Invalid maintenance cost.')
        else:
            costs[currency] = costs.get(currency, 0.0) + cost
    return {'by_stage': by_stage, 'measurement_ids': sorted(unique), 'known_cost_subtotals': costs,
            'complete_cost_totals': costs if unique and all(row['monetary_cost'] is not None
                and row['currency'] is not None for row in unique.values()) else None,
            'note': 'Local maintenance measurements exclude declared delegated calls; provider usage is reported separately. Missing prices are unknown.'}
