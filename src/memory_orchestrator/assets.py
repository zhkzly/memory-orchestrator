"""Compile exact candidate assets and execute caller-owned functional fixtures.

The default runner isolates files in a temporary working directory, not an OS
sandbox. A fixture requiring a sandbox is unknown without a capable provider.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path, PurePosixPath
import selectors
import signal
import subprocess
import sys
import tempfile
import time

from .schemas import DomainError, digest, new_id, validate
from .telemetry import measure_stage


def safe_path(value):
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or str(path) != value or '\\' in value
            or '..' in path.parts or any(ord(c) < 32 for c in value)):
        raise DomainError('asset_path', 'A fixture path must be relative and normalized', {'path': value})
    return value


def _execute_process(root, argv, stdin, timeout, limit):
    """Bound stdout/stderr together and kill the process group on timeout/overflow."""
    with tempfile.TemporaryFile() as input_stream:
        input_stream.write(stdin.encode('utf-8')); input_stream.seek(0)
        env = {'PATH': os.defpath, 'LANG': 'C.UTF-8', 'HOME': str(root),
               'TMPDIR': str(root), 'PYTHONDONTWRITEBYTECODE': '1'}
        proc = subprocess.Popen(argv, cwd=root, env=env, stdin=input_stream,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        output = {'stdout': bytearray(), 'stderr': bytearray()}
        reason, start = None, time.monotonic()
        try:
            with selectors.DefaultSelector() as selector:
                for name in output:
                    stream = getattr(proc, name); os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_READ, name)
                while selector.get_map():
                    if time.monotonic() - start >= timeout:
                        reason = 'timeout'; break
                    for key, _ in selector.select(min(.05, max(0, timeout - (time.monotonic() - start)))):
                        block = os.read(key.fileobj.fileno(), 8192)
                        if not block:
                            selector.unregister(key.fileobj); continue
                        remaining = limit - sum(map(len, output.values()))
                        output[key.data].extend(block[:max(0, remaining)])
                        if len(block) > remaining:
                            reason = 'output_limit'; break
                    if reason:
                        break
                if not reason:
                    try: proc.wait(timeout=max(.001, timeout - (time.monotonic() - start)))
                    except subprocess.TimeoutExpired: reason = 'timeout'
        finally:
            # Also remove descendants after a parent exits successfully.
            try: os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            proc.wait()
            proc.stdout.close(); proc.stderr.close()
        return {'returncode': proc.returncode, 'stdout': output['stdout'].decode('utf-8', 'replace'),
                'stderr': output['stderr'].decode('utf-8', 'replace'), 'interruption': reason}


def python_asset_runner(request, snapshot, test):
    """Trusted test expectations are checked by the host, never by the script."""
    if test['required_isolation'] != 'process':
        return {'available': False, 'reason': 'Default runner provides process isolation only.'}
    path = request['asset_path']
    if not path.endswith('.py'):
        return {'available': False, 'reason': 'Default functional runtime supports Python only.'}
    with tempfile.TemporaryDirectory(prefix='memory-asset-') as directory:
        root = Path(directory)
        for name, content in snapshot['assets'].items():
            target = root / safe_path(name); target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
        for name, content in test['input_files'].items():
            if name in snapshot['assets']:
                raise DomainError('fixture_overwrites_asset', 'Input fixture cannot replace candidate assets')
            target = root / safe_path(name); target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
        raw = _execute_process(root, [sys.executable, '-I', path, *test['args']], test['stdin'],
                               test['timeout_seconds'], test['max_output_bytes'])
        files, remaining = {}, test['max_output_bytes']
        for name in test['expected_files']:
            target = root / safe_path(name)
            if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(root):
                files[name] = None; continue
            with target.open('rb') as stream:
                value = stream.read(remaining + 1)
            if len(value) > remaining:
                raw['interruption'] = raw['interruption'] or 'output_file_limit'; files[name] = None
            else:
                files[name] = value.decode('utf-8', 'replace'); remaining -= len(value)
        raw.update(available=True, files=files)
        return raw


def decide_asset(kind, raw, test):
    if not isinstance(raw, dict) or raw.get('error') or not raw.get('available'):
        return 'unknown'
    if kind == 'compile':
        return ('pass' if raw['compiled'] else 'fail') if type(raw.get('compiled')) is bool else 'unknown'
    if raw.get('interruption'):
        return 'unknown'
    if test is None or (test['expected_stdout'] is None and not test['expected_files']):
        return 'unknown'
    if type(raw.get('returncode')) is not int:
        return 'unknown'
    passed = raw['returncode'] == 0
    if test['expected_stdout'] is not None:
        passed = passed and raw.get('stdout') == test['expected_stdout']
    passed = passed and all(raw.get('files', {}).get(name) == value for name, value in test['expected_files'].items())
    return 'pass' if passed else 'fail'


def run_assets(store, plan, materials, asset_runner=None, *, resolutions=None, comparison_id=None):
    from .evaluation import _raw, _error, _optional
    from .feedback import call_recorded
    snapshot = store.snapshot(plan['candidate_digest'])
    tests = {t['test_id']: t for t in materials['asset_tests']}
    records = []
    for job in plan['asset_jobs']:
        record_id='asset_check_'+digest([plan['verification_plan_id'],job['job_id']])
        existing=_optional(store,'asset_checks',record_id)
        if existing is not None:
            records.append(existing);continue
        test = tests.get(job['test_id'])
        request = {'request_id': job['job_id'], 'asset_path': job['asset_path'], 'kind':job['kind'],
                   'snapshot_digest': plan['candidate_digest'], 'verification_plan_ref': plan['verification_plan_id']}
        runner = ({'id': 'python-compile', 'version': sys.version} if job['kind'] == 'compile' and job['asset_path'].endswith('.py')
                  else materials['asset_runner'])
        usages, gaps, raw = [], [], None
        with measure_stage(store, plan['project_id'], 'validate_overhead', purpose='validation', subject_ref=job['job_id']) as meter:
            try:
                if job['kind'] == 'compile' and job['asset_path'].endswith('.py'):
                    try:
                        compile(snapshot['assets'][job['asset_path']], job['asset_path'], 'exec')
                        raw = {'available': True, 'compiled': True}
                    except (SyntaxError, ValueError) as exc:
                        raw = {'available': True, 'compiled': False, 'diagnostics': _error(exc)}
                elif job['kind']=='compile' and asset_runner is None:
                    raw = {'available': False, 'reason': 'No compile capability for this script language.'}
                elif job['kind']=='function' and test is None:
                    raw = {'available': False, 'reason': 'Missing independent functional fixture.'}
                elif test and test['required_isolation'] == 'sandbox' and (asset_runner is None or runner['isolation'] != 'sandbox'):
                    raw = {'available': False, 'reason': 'Required sandbox capability is unavailable.'}
                else:
                    callback = asset_runner or python_asset_runner
                    args = copy.deepcopy([request, snapshot, test])
                    started = time.monotonic()
                    try:
                        actual=call_recorded(store,project_id=plan['project_id'],batch_id=comparison_id,run_id=None,
                            request_ref=job['job_id']+':asset',stage='execute',config={'runner':runner,'test_hash':digest(test),'bundle_hash':digest(snapshot)},
                            purpose='validation',subject_ref=job['job_id'],callback=callback,args=args,resolutions=resolutions)
                        raw={'available':False,'error':actual['error'],'returned':actual['raw_output']} if actual['error'] else actual['raw_output']
                        if not isinstance(raw,dict):raw={'available':False,'error':'Asset provider did not return an object.','returned':_raw(raw)}
                        for key in ('request_id','asset_path','snapshot_digest'):
                            if key in raw and raw[key]!=request[key]:
                                raw={'available':False,'error':'Asset provider returned a mismatched '+key,'returned':raw}
                                break
                        raw={**raw,'attempt_ref':actual['attempt_id']}
                        usages.extend(actual['usage_refs'])
                    finally:
                        elapsed = time.monotonic() - started; meter.exclude(elapsed)
            except Exception:
                # An interrupted ledger boundary is recoverable, not evidence
                # that the script was never run or that a retry is safe.
                raise
            status = decide_asset(job['kind'], raw, test)
            if status != 'pass': gaps.append(str(raw.get('reason') or raw.get('error') or status))
            record = {'asset_check_id': record_id, 'project_id': plan['project_id'],
                      'verification_plan_ref': plan['verification_plan_id'], 'job_id': job['job_id'],
                      'candidate_digest': plan['candidate_digest'], 'bundle_hash': digest(snapshot),
                      'asset_path': job['asset_path'], 'asset_hash': digest(snapshot['assets'][job['asset_path']]),
                      'kind': job['kind'], 'test_id': job['test_id'], 'test_hash': digest(test) if test else None,
                      'runner': runner, 'request': request, 'raw': _raw(raw), 'status': status, 'gaps': gaps,
                      'usage_refs': usages}
            validate('AssetCheckRecord', record)
            store.put('asset_checks', record['asset_check_id'], record); records.append(record)
    return verify_assets(store,plan,materials,records)


def verify_assets(store, plan, materials, records):
    """Recompute output checks against exact frozen fixtures and full bundle hash."""
    snapshot = store.snapshot(plan['candidate_digest'])
    tests = {t['test_id']: t for t in materials['asset_tests']}
    jobs = {j['job_id']: j for j in plan['asset_jobs']}
    if len(records) != len(jobs) or {r['job_id'] for r in records} != set(jobs):
        raise DomainError('asset_coverage', 'Required asset checks missing or duplicated')
    for record in records:
        validate('AssetCheckRecord', record)
        job, test = jobs[record['job_id']], tests.get(record['test_id'])
        expected = {'verification_plan_ref': plan['verification_plan_id'], 'candidate_digest': plan['candidate_digest'],
                    'project_id': plan['project_id'], 'bundle_hash': digest(snapshot), 'asset_path': job['asset_path'],
                    'asset_hash': digest(snapshot['assets'][job['asset_path']]), 'kind': job['kind'],
                    'test_id': job['test_id'], 'test_hash': digest(test) if test else None}
        if any(record[key] != value for key, value in expected.items()) or record['status'] != decide_asset(job['kind'], record['raw'], test):
            raise DomainError('asset_binding', 'Asset result differs from exact bundle, fixture or observed output')
        expected_request={'request_id':job['job_id'],'asset_path':job['asset_path'],'kind':job['kind'],
                          'snapshot_digest':plan['candidate_digest'],'verification_plan_ref':plan['verification_plan_id']}
        if record['request']!=expected_request:
            raise DomainError('asset_request','Asset result describes a different planned input')
        if record['kind']=='function' and record['runner']!=materials['asset_runner']:
            raise DomainError('asset_runner','Functional runner identity/configuration changed')
        if record['raw'].get('attempt_ref'):
            original=store.get('callback_returns',record['raw']['attempt_ref'])
            expected_raw=({'available':False,'error':original['error'],'returned':original['raw_output']}
                          if original['error'] else original['raw_output'])
            if not isinstance(expected_raw,dict):
                expected_raw={'available':False,'error':'Asset provider did not return an object.','returned':expected_raw}
            for key in ('request_id','asset_path','snapshot_digest'):
                if key in expected_raw and expected_raw[key]!=expected_request[key]:
                    expected_raw={'available':False,'error':'Asset provider returned a mismatched '+key,'returned':expected_raw}
                    break
            attempt=store.get('callback_attempts',original['attempt_id'])
            if (original['project_id']!=plan['project_id'] or original['request_ref']!=job['job_id']+':asset'
                    or record['raw']!={**expected_raw,'attempt_ref':original['attempt_id']}
                    or attempt['config_hash']!=digest({'runner':record['runner'],'test_hash':digest(test),'bundle_hash':digest(snapshot)})):
                raise DomainError('asset_execution','Functional evidence differs from original executed callback')
        elif record['kind']=='function' and record['status']!='unknown':
            raise DomainError('asset_execution','Known functional result requires an actual recorded execution')
        for uid in record['usage_refs']:
            usage = store.get('usage', uid)
            if usage['project_id'] != plan['project_id'] or usage.get('request_id') != job['job_id']:
                raise DomainError('asset_usage', 'Asset usage belongs to another check')
    return records
