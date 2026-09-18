"""Exact single-edge injections used only by the official mutation-license tool."""
from pathlib import Path
import sys

CASES = {
    "trace_cold_hash": ("trace.py", 'or _hash_file(paths["raw_path"]) != manifest["raw_sha256"]', 'or False'),
    "trace_batch_cap": ("trace.py", 'while added < limits["max_events"] and original.tell() - start < limits["max_bytes"]:',
                        'while original.tell() - start < limits["max_bytes"]:'),
    "trace_byte_range": ("trace.py", 'block[max(0, absolute_start-offset):min(size, absolute_end-offset)]',
                         'block[0:min(size, absolute_end-offset)]'),
    "trace_hot_identity": ("trace.py", 'if any((p.stat().st_dev, p.stat().st_ino, p.stat().st_size, p.stat().st_mtime_ns)',
                            'if False and any((p.stat().st_dev, p.stat().st_ino, p.stat().st_size, p.stat().st_mtime_ns)'),
    "goal_user_anchor": ("goals.py", 'anchor is None or anchor["source_role"] != "user" or anchor["source_kind"] != "instruction"',
                         'anchor is None or anchor["source_kind"] != "instruction"'),
    "goal_future_window": ("goals.py", 'packet[key] = [item for item in packet[key] if in_window(item)]', 'packet[key] = packet[key]'),
    "maintenance_commit": ("maintenance.py", 'active = {}', 'active = {key: row for key, row in records.items() if row["op"] != "REVOKE"}'),
    "maintenance_conflict": ("maintenance.py", 'if any(r["op"] == "MARK_CONFLICT"', 'if False and any(r["op"] == "MARK_CONFLICT"'),
    "necessity_noop": ("learning.py", 'if diagnosis["necessity"]["verdict"] != "proceed":', 'if False:'),
    "necessity_add": ("learning.py", 'if any(op["op"] not in operations for op in value["operations"]):', 'if False:'),
    "failure_ranking": ("learning.py", 'score = lexical + failure', 'score = lexical'),
    "maintenance_consumer": ("learning.py", 'if comparison["pairs"] or comparison["existing_relations"]:', 'if False:'),
    "archive_parent": ("learning.py", '    while True:\n        unresolved = _unique', '    while False:\n        unresolved = _unique'),
    "derived_projection": ("evidence.py", 'for row in index["goal_annotations"]', 'for row in []'),
    "resource_candidate": ("evidence.py", '"declared_parent" if parent else "same_resource_candidate"', '"declared_parent"'),
    "check_reference": ("learning.py", '    available = {row["check_ref"]: row for row in catalog}',
                        '    return  # MUTANT removes the public-directory binding\n    available = {row["check_ref"]: row for row in catalog}'),
    "fee_amount": ("learning.py", '"monetary_cost": entry.get("monetary_cost")', '"monetary_cost": None'),
    "fee_currency": ("learning.py", '"currency": entry.get("currency")', '"currency": None'),
    "fee_price_version": ("learning.py", '"price_version": entry.get("price_version")', '"price_version": None'),
    "interrupted_wait": ("learning.py", 'meter.exclude(time.monotonic() - call_started)', 'meter.exclude(0.0)'),
}

if __name__ == "__main__":
    filename, before, after = CASES[sys.argv[1]]
    path = Path("src/memory_orchestrator") / filename
    source = path.read_text()
    if source.count(before) != 1:
        raise SystemExit("Mutation anchor must match exactly once: " + sys.argv[1])
    path.write_text(source.replace(before, after))
