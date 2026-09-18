"""One authorized SDK integration cycle; fixed synthetic CSV data, not a benchmark."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

from examples.memory_evolution.demo import run_demo
from memory_orchestrator.model import StructuredModel, make_openai_call
from memory_orchestrator.schemas import DomainError, load_contracts
from memory_orchestrator.store import Store


if __name__ == '__main__':
    here = Path(__file__).resolve().parent
    repo = next(path for path in here.parents if (path / '.trellis').is_dir() and (path / 'src/memory_orchestrator').is_dir())
    destination = here / 'live-canary'
    destination.mkdir(exist_ok=True)
    config = {'model': 'gpt-5.6-terra', 'base_url': 'http://localhost:8317/v1', 'timeout': 30,
              'max_calls': 8, 'max_input_chars': 120000, 'max_total_input_chars': 480000,
              'max_output_chars': 20000, 'max_output_tokens': 4000, 'max_format_repairs': 1}
    source = {str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted((repo / 'src/memory_orchestrator').iterdir()) if path.suffix in ('.py', '.json')}
    root = tempfile.mkdtemp(prefix='memory-full-live-')
    summary = {'kind': 'bounded real SDK wiring with synthetic CSV tasks; not benchmark evidence',
               'config': config, 'contract_source': load_contracts()['source'], 'source_hashes': source,
               'store_root': root, 'status': 'started', 'rounds': 1}
    (destination / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    started = time.monotonic()
    model = None
    try:
        if not os.environ.get('OPENAI_API_KEY'):
            raise DomainError('missing_environment', 'OPENAI_API_KEY is absent; no request was sent.')
        model = StructuredModel(make_openai_call(model=config['model'], base_url=config['base_url'], timeout=config['timeout']),
            limits={key: config[key] for key in ('max_calls', 'max_input_chars', 'max_total_input_chars',
                                                'max_output_chars', 'max_output_tokens', 'max_format_repairs')})
        result = run_demo(root, model=model, rounds=1)
        (destination / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        summary.update(status='returned', learning_statuses=result['learning_statuses'],
                       release_count=result['release_count'], usage=result['report']['usage'],
                       validation_attempt_counts=result['report']['validation_attempt_counts'])
    except BaseException as exc:
        summary.update(status='interrupted' if not isinstance(exc, Exception) else 'error',
                       error={'type': type(exc).__name__, 'code': getattr(exc, 'code', None)})
        # No SDK error message, environment value or credential is persisted.
    finally:
        store = Store(root)
        for kind in ('learning_cycles', 'errors', 'usage', 'reports', 'candidates', 'validations', 'releases'):
            (destination / (kind + '.json')).write_text(json.dumps(store.list(kind), ensure_ascii=False, indent=2) + '\n')
        summary.update(elapsed_seconds=time.monotonic() - started, model_calls=model.calls if model else 0)
        (destination / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({k: summary[k] for k in ('status', 'model_calls', 'elapsed_seconds')}, ensure_ascii=False), flush=True)
        print(json.dumps({k: summary.get(k) for k in ('learning_statuses', 'release_count', 'error')}, ensure_ascii=False), flush=True)
