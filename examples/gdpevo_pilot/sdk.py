"""Physical SDK call recording and one fixed budget for this diagnostic pilot."""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import tempfile
import time

from memory_orchestrator.schemas import DomainError, digest, now_iso


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.pending-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump(value, output, ensure_ascii=False, indent=2, allow_nan=False)
            output.write('\n'); output.flush(); os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class CallLedger:
    def __init__(self, root, *, config, client=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.config = deepcopy(config)
        for key in ('max_calls', 'max_total_input_chars', 'max_output_tokens'):
            if type(config.get(key)) is not int or config[key] < 1:
                raise DomainError('pilot_budget', 'Explicit positive pilot budget required: ' + key)
        with self._lock():
            path = self.root / 'config.json'
            if path.exists():
                if json.loads(path.read_text()) != config:
                    raise DomainError('pilot_frozen_config', 'Use a new study for a different physical-call budget.')
            else:
                save_json(path, config)
        if client is None:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'), base_url=config['base_url'],
                            timeout=config['timeout'], max_retries=0)
        self.client = client

    @contextmanager
    def _lock(self):
        with (self.root / '.calls.lock').open('a') as file:
            fcntl.flock(file, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(file, fcntl.LOCK_UN)

    def starts(self):
        return [json.loads(path.read_text()) for path in sorted(self.root.glob('*.start.json'))]

    def __call__(self, payload, *, stage, subject):
        payload = deepcopy(payload)
        allowed = {'messages', 'tools', 'tool_choice', 'parallel_tool_calls', 'response_format',
                   'max_completion_tokens', 'temperature'}
        if set(payload) - allowed:
            raise DomainError('pilot_request', 'Only declared chat payload fields are accepted.')
        cap = payload.get('max_completion_tokens')
        if type(cap) is not int or not 0 < cap <= self.config['max_output_tokens']:
            raise DomainError('pilot_budget', 'Requested output exceeds the fixed pilot budget.')
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        with self._lock():
            previous = self.starts()
            if (len(previous) >= self.config['max_calls'] or
                    len(serialized) + sum(row['input_chars'] for row in previous) > self.config['max_total_input_chars']):
                raise DomainError('pilot_budget', 'Physical-call or total-input budget exhausted before dispatch.')
            identifier = f'call_{len(previous) + 1:04d}'
            record = {'call_ref': identifier, 'stage': stage, 'subject': subject, 'started_at': now_iso(),
                      'input_chars': len(serialized), 'payload_hash': digest(payload), 'payload': payload,
                      'char_measure': 'serialized complete messages, tools and call options; not tokenizer counts'}
            save_json(self.root / (identifier + '.start.json'), record)
        start = time.monotonic()
        try:
            response = self.client.chat.completions.create(model=self.config['model'], timeout=self.config['timeout'], **payload)
            raw = response if isinstance(response, dict) else response.model_dump(mode='json')
            public = {key: deepcopy(raw.get(key)) for key in ('id', 'model', 'usage')}
            public['choices'] = [{'finish_reason': choice.get('finish_reason'), 'message': {
                key: deepcopy(choice.get('message', {}).get(key)) for key in ('role', 'content', 'tool_calls', 'refusal')
                if key in choice.get('message', {})}} for choice in raw.get('choices', [])]
        except BaseException as exc:
            save_json(self.root / (identifier + '.return.json'), {'call_ref': identifier, 'status': 'error',
                'error_type': type(exc).__name__, 'elapsed_seconds': time.monotonic() - start,
                'usage': None, 'finished_at': now_iso()})
            raise
        elapsed = time.monotonic() - start
        save_json(self.root / (identifier + '.return.json'), {'call_ref': identifier, 'status': 'returned',
            'response': public, 'usage': public.get('usage'), 'elapsed_seconds': elapsed, 'finished_at': now_iso()})
        return {**public, 'call_ref': identifier, 'elapsed_seconds': elapsed}

    def teacher_invoke(self, subject):
        def invoke(request):
            raw = self({'messages': request['messages'], 'response_format': {'type': 'json_object'},
                        'max_completion_tokens': request['max_output_tokens']},
                       stage=request['prompt_id'], subject=subject)
            choice = (raw.get('choices') or [{}])[0]
            usage = raw.get('usage')
            return {'text': choice.get('message', {}).get('content'), 'finish_reason': choice.get('finish_reason'),
                    'model': raw.get('model'), 'request_id': raw.get('id'), 'usage': None if usage is None else {
                        'input_tokens': usage.get('prompt_tokens'), 'output_tokens': usage.get('completion_tokens'),
                        'total_tokens': usage.get('total_tokens'),
                        **{key: usage[key] for key in ('monetary_cost', 'currency', 'price_version') if key in usage}}}
        return invoke

    def summary(self):
        starts = self.starts()
        returns = {row['call_ref']: row for path in self.root.glob('*.return.json')
                   if (row := json.loads(path.read_text()))}
        names = ('prompt_tokens', 'completion_tokens', 'total_tokens')
        known = {name: [] for name in names}
        rows = []
        for start in starts:
            returned = returns.get(start['call_ref'], {})
            usage = returned.get('usage') or {}
            for name in names:
                value = usage.get(name)
                if type(value) is int and value >= 0:
                    known[name].append(value)
            rows.append({key: start[key] for key in ('call_ref', 'stage', 'subject', 'input_chars')}
                        | {'status': returned.get('status', 'unreturned'), 'usage': usage or None,
                           'elapsed_seconds': returned.get('elapsed_seconds')})
        complete = bool(starts) and all(len(known[name]) == len(starts) for name in names)
        return {'calls': len(starts), 'input_chars': sum(row['input_chars'] for row in starts), 'records': rows,
                'known_token_subtotals': {name: sum(values) if values else None for name, values in known.items()},
                'complete_token_totals': {name: sum(values) for name, values in known.items()} if complete else None,
                'unknown_usage_calls': sum(row['usage'] is None for row in rows),
                'monetary_cost': None, 'cost_note': 'No price was supplied for this pilot; no price is inferred from tokens.'}
