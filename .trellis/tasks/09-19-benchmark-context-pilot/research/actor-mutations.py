"""Exact actor.py injections, run only by the official mutation-license tool."""
from pathlib import Path
import sys

STATE_LINE = '            current_messages = deepcopy(messages) + [{"role": "system", "content": "HOST_EXECUTION_STATE\\n" + _json(host_state)}]'
CASES = {
    'public_file_scope': ('_require(path in files, "input_not_public"', '_require(True, "input_not_public"'),
    'business_get_scope': ('and _business_path(args.get("path")), "business_endpoint"', 'and True, "business_endpoint"'),
    'tool_id_pairing': ('messages.append({"role": "tool", "tool_call_id": item["id"], "content": text})',
                        'messages.append({"role": "tool", "tool_call_id": "unbound", "content": text})'),
    'input_budget': ('if input_chars > caps["max_input_chars"]:', 'if False:'),
    'tool_budget': ('over_tools = tool_count + len(tool_calls) > caps["max_tool_calls"]', 'over_tools = False'),
    'asset_read_consumption': ('if asset is not None and output["status"] == "ok":', 'if False:'),
    'selected_asset_scope': ('and args["path"] in assets, "asset_not_selected"', 'and args["path"] in snapshot["assets"], "asset_not_selected"'),
    'length_termination': ('return finish("budget_exhausted", artifact=content, has_artifact=content is not None, reason="SDK output-token limit',
                          'return finish("completed", artifact=content, has_artifact=content is not None, reason="SDK output-token limit'),
    'stop_raw_artifact': ('return finish("completed", artifact=content, has_artifact=True,', 'return finish("completed", artifact={}, has_artifact=True,'),
    'host_state_visible': (STATE_LINE, '            current_messages = deepcopy(messages)'),
    'remaining_call_count': ('remaining = caps["max_model_calls"] - turn - 1', 'remaining = caps["max_model_calls"] - turn'),
    'no_stale_state_history': (STATE_LINE,
        '            messages.append({"role": "system", "content": "HOST_EXECUTION_STATE\\n" + _json(host_state)})\n'
        '            current_messages = deepcopy(messages)'),
    'host_state_input_budget': ('input_chars = len(_json(payload))', 'input_chars = len(_json({**payload, "messages": messages}))'),
    'sdk_id_type_first': (
        'if (len(identifiers) != len(tool_calls) or any(not isinstance(identifier, str) or not identifier for identifier in identifiers)\n'
        '                    or len(set(identifiers)) != len(identifiers)',
        'if (len(identifiers) != len(tool_calls) or len(set(identifiers)) != len(identifiers)\n'
        '                    or any(not isinstance(identifier, str) or not identifier for identifier in identifiers)'),
}

if __name__ == '__main__':
    path = Path('examples/gdpevo_pilot/actor.py')
    before, after = CASES[sys.argv[1]]
    source = path.read_text()
    if source.count(before) != 1:
        raise SystemExit('Expected exactly one mutation anchor: ' + sys.argv[1])
    path.write_text(source.replace(before, after))
