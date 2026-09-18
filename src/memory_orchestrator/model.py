"""Finite structured model calls through a plain callable, with explicit accounting."""
from __future__ import annotations

import copy
import json
import math
import os
import re
import time

from .schemas import DomainError, digest, load_contracts, new_id, validate


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _token_count(value):
    return value if type(value) is int and value >= 0 else None


class StructuredModel:
    """A per-learning-cycle call budget, not a model backend registry.

    ``invoke(request)`` returns ``text``, ``finish_reason``, optional ``usage`` and
    model/request identity. All limits are explicitly supplied by the caller.
    """
    def __init__(self, invoke, *, limits):
        names = ("max_input_chars", "max_output_chars", "max_output_tokens",
                 "max_total_input_chars", "max_calls", "max_format_repairs")
        for name in names:
            value = limits.get(name)
            if type(value) is not int or value < (0 if name == "max_format_repairs" else 1):
                raise DomainError("invalid_model_budget", f"Explicit integer {name} is required.")
        if not callable(invoke):
            raise DomainError("invalid_model_callable", "Provide a callable model operation.")
        self.invoke = invoke
        self.limits = {key: limits[key] for key in names}
        self.calls = 0
        self.input_chars = 0
        self.output_chars = 0

    def _visible_limits(self):
        return {**self.limits, "remaining_calls": self.limits["max_calls"] - self.calls,
                "remaining_input_chars": self.limits["max_total_input_chars"] - self.input_chars,
                "input_measure": "serialized message characters, not measured tokens"}

    def generate(self, prompt_id, inputs, *, check=None):
        """Run optional pure semantic validation inside the same finite repair loop.

        ``check`` must not persist changes or execute a candidate. It receives a
        copy; its DomainError is repair feedback, never an extra retry allowance.
        """
        if check is not None and not callable(check):
            raise DomainError("invalid_model_check", "Semantic check must be a pure callable or None.")
        contracts = load_contracts()
        if prompt_id not in contracts["prompts"]:
            raise DomainError("unknown_prompt", "Prompt must be in the packaged source contract.")
        prompt = contracts["prompts"][prompt_id]
        schema_id = prompt["output_schema"]
        schema = contracts["schemas"][schema_id]
        fields = set(prompt["input_fields"]) - {"output_schema"}
        if not isinstance(inputs, dict) or set(inputs) - {"output_schema"} != fields:
            raise DomainError("prompt_input_mismatch", "Provide every declared prompt input and no extra fields.",
                              {"expected_fields": sorted(fields), "actual_fields": sorted(inputs) if isinstance(inputs, dict) else []})
        if "output_schema" in inputs and inputs["output_schema"] != schema:
            raise DomainError("prompt_schema_mismatch", "Output schema cannot be weakened by a caller.")
        values = copy.deepcopy(inputs)
        values["output_schema"] = schema
        for name in ("extraction_limits", "learning_limits"):
            if name in fields:
                if not isinstance(values[name], dict):
                    raise DomainError("invalid_model_budget", f"{name} must explicitly describe this learning protocol.")
                for key, limit in self.limits.items():
                    if key in values[name] and values[name][key] != limit:
                        raise DomainError("model_budget_mismatch", f"Visible {key} disagrees with the enforced call limit.")
                values[name].update(self._visible_limits())
        if schema_id == "ExtractionDraft":
            for name in ("max_experiences", "max_read_requests", "max_evidence_expansions"):
                if type(values["extraction_limits"].get(name)) is not int or values["extraction_limits"][name] < 0:
                    raise DomainError("invalid_model_budget", f"Explicit nonnegative extraction_limits.{name} is required.")
        template_fields = set(re.findall(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", prompt["user_template"]))
        if template_fields != set(prompt["input_fields"]):
            raise DomainError("prompt_contract_mismatch", "Packaged template and input fields disagree.")
        user = re.sub(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", lambda match: _json(values[match[1]]), prompt["user_template"])
        user += "\nHost-enforced call limits (characters are not tokens): " + _json(self._visible_limits())
        messages = [{"role": "system", "content": prompt["system"]}, {"role": "user", "content": user}]
        usage, attempts = [], []

        def fail(code, message, **details):
            raise DomainError(code, message, {"prompt_id": prompt_id, "usage": copy.deepcopy(usage),
                "attempts": copy.deepcopy(attempts), "calls_consumed": self.calls,
                "input_chars_consumed": self.input_chars, **details})

        for repair in range(self.limits["max_format_repairs"] + 1):
            count = len(_json(messages))
            if (self.calls >= self.limits["max_calls"] or count > self.limits["max_input_chars"]
                    or self.input_chars + count > self.limits["max_total_input_chars"]):
                fail("model_budget_exhausted", "Call or input-character budget exhausted before the next attempt.",
                     requested_input_chars=count, limits=copy.deepcopy(self.limits))
            self.calls += 1
            self.input_chars += count
            started = time.monotonic()
            entry = {"usage_id": new_id("modelcall"), "prompt_id": prompt_id,
                     "attempt": repair + 1, "input_chars": count, "output_chars": None,
                     "input_tokens": None, "output_tokens": None, "total_tokens": None,
                     "measurement": "missing", "model": None, "request_id": None,
                     "elapsed_seconds": None, "status": "attempted"}
            usage.append(entry)
            try:
                response = self.invoke({"prompt_id": prompt_id, "messages": copy.deepcopy(messages),
                                        "max_output_tokens": self.limits["max_output_tokens"]})
            except Exception as exc:
                entry.update(status="transport_error", elapsed_seconds=time.monotonic() - started)
                # SDK transport messages may embed credentials/headers; retain type, not their text.
                attempts.append({"attempt": repair + 1, "error_type": type(exc).__name__, "status": "transport_error"})
                fail("model_transport_error", "Model callable failed; actual token usage is unknown.",
                     error_type=type(exc).__name__)
            entry["elapsed_seconds"] = time.monotonic() - started
            if not isinstance(response, dict):
                attempts.append({"attempt": repair + 1, "status": "invalid_response"})
                fail("invalid_model_response", "Callable must return a structured response envelope.")
            response = {key: copy.deepcopy(response.get(key)) for key in ("text", "finish_reason", "usage", "model", "request_id")}
            reported = response.get("usage")
            if isinstance(reported, dict):
                diagnostics = []
                for key in ("input_tokens", "output_tokens", "total_tokens"):
                    original = reported.get(key)
                    entry[key] = _token_count(original)
                    if original is not None and entry[key] is None:
                        diagnostics.append({"path": "usage." + key, "expected": "nonnegative integer or null",
                            "reported_type": type(original).__name__,
                            "reported_value": repr(original) if type(original) in (int, float, bool) else "<non-numeric value>"})
                # Retain a JSON-safe diagnostic instead of poisoning the shared ledger
                # (NaN is not JSON, and fractional/bool token counts are not counts).
                response["usage"] = {key: entry[key] for key in ("input_tokens", "output_tokens", "total_tokens")}
                if diagnostics:
                    entry["usage_diagnostics"] = diagnostics
                if any(entry[key] is not None for key in ("input_tokens", "output_tokens", "total_tokens")):
                    entry["measurement"] = "partial" if diagnostics else "provider_reported"
            entry["model"] = response.get("model")
            entry["request_id"] = response.get("request_id")
            text = response.get("text")
            if isinstance(text, str):
                entry["output_chars"] = len(text)
                self.output_chars += len(text)
            attempts.append({"attempt": repair + 1, "finish_reason": response.get("finish_reason"),
                             "raw_response": copy.deepcopy(response)})
            if isinstance(text, str) and len(text) > self.limits["max_output_chars"]:
                attempts[-1]["raw_response"]["text"] = text[:self.limits["max_output_chars"]]
                attempts[-1]["raw_response_truncated"] = True
                attempts[-1]["raw_response_hash"] = digest(text)
            if response.get("finish_reason") != "stop":
                entry["status"] = "truncated" if response.get("finish_reason") == "length" else "incomplete"
                fail("model_truncated" if entry["status"] == "truncated" else "model_incomplete", "Response did not finish normally.")
            if not isinstance(text, str):
                entry["status"] = "invalid_response"
                fail("invalid_model_response", "Response text is missing.")
            if len(text) > self.limits["max_output_chars"] or (
                entry["output_tokens"] is not None and entry["output_tokens"] > self.limits["max_output_tokens"]
            ):
                entry["status"] = "output_budget_exhausted"
                fail("model_output_budget_exhausted", "Response exceeded the explicit output-character limit.")
            try:
                def invalid_constant(value):
                    raise ValueError(f"Non-JSON numeric constant {value}")
                value = json.loads(text, parse_constant=invalid_constant)
                value = validate(schema_id, value)
                if schema_id == "ExtractionDraft":
                    errors = []
                    for key, limit_name in (("experiences", "max_experiences"), ("read_requests", "max_read_requests")):
                        maximum = values["extraction_limits"][limit_name]
                        if len(value[key]) > maximum:
                            errors.append({"path": "$." + key, "actual_count": len(value[key]), "maximum": maximum})
                    if value["status"] == "needs_more_evidence" and values["extraction_limits"]["max_evidence_expansions"] == 0:
                        errors.append({"path": "$.status", "actual": "needs_more_evidence", "expected": "completed or abstained; no expansions remain"})
                    if errors:
                        raise DomainError("extraction_limit_exceeded", "Draft exceeds visible extraction limits.", {"errors": errors})
                if check is not None:
                    check(copy.deepcopy(value))
            except (json.JSONDecodeError, ValueError, DomainError) as exc:
                entry["status"] = "invalid_output"
                details = {**exc.details, "code": exc.code, "message": exc.message} if isinstance(exc, DomainError) else {"errors": [{"path": "$", "message": str(exc)}]}
                attempts[-1]["diagnostics"] = copy.deepcopy(details)
                if repair == self.limits["max_format_repairs"]:
                    fail("invalid_output", "Response is not valid under the schema and declared limits.", diagnostics=details)
                messages += [{"role": "assistant", "content": text}, {"role": "user", "content":
                    "Correct the rejected JSON using the original schema and inputs. Return only JSON. "
                    "Resolve all listed paths; do not invent evidence. Diagnostics: " + _json(details)
                    + "\nCurrent enforced limits: " + _json(self._visible_limits())}]
                continue
            entry["status"] = "completed"
            result = {"value": value, "usage": copy.deepcopy(usage), "raw_response": copy.deepcopy(response), "attempts": attempts}
            if prompt_id == "proxy_judge_v1":
                result["source"] = "llm_proxy"
            return result
        raise AssertionError("finite repair loop must return or raise")


def make_openai_call(*, timeout, model="gpt-5.6-terra", base_url=None, api_key=None, client=None):
    """Return a plain OpenAI SDK callable; never log credentials or hidden reasoning."""
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise DomainError("invalid_model_timeout", "Provide a positive finite timeout.")
    if client is None:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url or os.environ.get("OPENAI_BASE_URL") or "http://localhost:8317/v1",
            timeout=timeout, max_retries=0,
        )
    elif hasattr(client, "with_options"):
        client = client.with_options(timeout=timeout, max_retries=0)

    def invoke(request):
        cap = request.get("max_output_tokens")
        if type(cap) is not int or cap <= 0:
            raise DomainError("invalid_model_budget", "An explicit positive output-token limit is required.")
        completion = client.chat.completions.create(
            model=model, messages=request["messages"], response_format={"type": "json_object"},
            max_completion_tokens=cap, timeout=timeout,
        )
        raw = completion if isinstance(completion, dict) else completion.model_dump(mode="json")
        choices = raw.get("choices") or []
        first = choices[0] if choices else {}
        message = first.get("message") or {}
        usage = raw.get("usage")
        return {"text": message.get("content"), "finish_reason": first.get("finish_reason"),
                "model": raw.get("model", model), "request_id": raw.get("id"),
                "usage": None if not isinstance(usage, dict) else {
                    "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
                    "total_tokens": usage.get("total_tokens")}}
    return invoke
