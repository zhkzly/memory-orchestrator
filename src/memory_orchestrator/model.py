"""Finite structured model calls through a plain callable, with explicit accounting."""
from __future__ import annotations

import copy
import json
import math
import os
import re
import threading
import time

from .schemas import DomainError, digest, load_contracts, new_id, normalize_usage_measurements, validate


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _token_count(value):
    return value if type(value) is int and value >= 0 else None


def _default_token_estimate(messages):
    """A disclosed estimate over full messages, not a tokenizer or upper bound."""
    return math.ceil(len(_json(messages).encode("utf-8")) / 3)


def _token_budget(value, counter):
    required = {"max_input_tokens", "max_total_input_tokens", "max_total_output_tokens", "stages"}
    if not isinstance(value, dict) or required - value.keys() or value.keys() - required - {"counter_id", "count_kind"}:
        raise DomainError("invalid_model_budget", "Provide the declared global token limits and prompt stages only.")
    result = copy.deepcopy(value)
    if counter is not None and (not result.get("counter_id") or not result.get("count_kind")):
        raise DomainError("invalid_model_budget", "An injected counter requires explicit counter_id and count_kind.")
    result.setdefault("counter_id", "utf8-json-bytes-div3-v1")
    result.setdefault("count_kind", "documented_estimate")
    if (not isinstance(result["counter_id"], str) or not result["counter_id"].strip()
            or result["count_kind"] not in ("tokenizer_estimate", "documented_estimate")):
        raise DomainError("invalid_model_budget", "Counter identity and its estimate method must be explicit.")
    if counter is None and (result["counter_id"] != "utf8-json-bytes-div3-v1" or result["count_kind"] != "documented_estimate"):
        raise DomainError("invalid_model_budget", "The default counter is utf8-json-bytes-div3-v1, a documented estimate.")
    for key in required - {"stages"}:
        if type(result[key]) is not int or result[key] < 0:
            raise DomainError("invalid_model_budget", f"token_budget.{key} must be a nonnegative integer.")
    if not isinstance(result["stages"], dict):
        raise DomainError("invalid_model_budget", "Token stages must map registered prompt IDs to limits.")
    fields = {"max_calls", "max_input_tokens", "max_output_tokens", "max_total_input_tokens", "max_total_output_tokens"}
    prompts = load_contracts()["prompts"]
    for prompt_id, stage in result["stages"].items():
        if prompt_id not in prompts or not isinstance(stage, dict) or set(stage) != fields:
            raise DomainError("invalid_model_budget", "Each token stage needs a registered prompt and all five limits.")
        if any(type(stage[key]) is not int or stage[key] < 0 for key in fields):
            raise DomainError("invalid_model_budget", "Stage token and call limits must be nonnegative integers.")
    return result


class StructuredModel:
    """A per-learning-cycle call budget, not a model backend registry.

    ``invoke(request)`` returns ``text``, ``finish_reason``, optional ``usage`` and
    model/request identity. All limits are explicitly supplied by the caller.
    """
    def __init__(self, invoke, *, limits, token_counter=None):
        names = ("max_input_chars", "max_output_chars", "max_output_tokens",
                 "max_total_input_chars", "max_calls", "max_format_repairs")
        for name in names:
            value = limits.get(name)
            if type(value) is not int or value < (0 if name == "max_format_repairs" else 1):
                raise DomainError("invalid_model_budget", f"Explicit integer {name} is required.")
        if not callable(invoke):
            raise DomainError("invalid_model_callable", "Provide a callable model operation.")
        if token_counter is not None and not callable(token_counter):
            raise DomainError("invalid_model_budget", "token_counter must be a callable or None.")
        if token_counter is not None and "token_budget" not in limits:
            raise DomainError("invalid_model_budget", "An injected token counter needs a frozen token_budget identity.")
        self.invoke = invoke
        self.limits = {key: copy.deepcopy(limits[key]) for key in names}
        if "token_budget" in limits:
            self.limits["token_budget"] = _token_budget(limits["token_budget"], token_counter)
        self._count_tokens = token_counter or _default_token_estimate
        self._budget_lock = threading.RLock()
        self._token_spent = {"input": 0, "output": 0}
        self._stage_spent = {}
        self._token_overrun = None
        self.calls = 0
        self.input_chars = 0
        self.output_chars = 0

    def _visible_limits(self):
        result = {**copy.deepcopy(self.limits), "remaining_calls": self.limits["max_calls"] - self.calls,
                "remaining_input_chars": self.limits["max_total_input_chars"] - self.input_chars,
                "input_measure": "serialized message characters, not measured tokens"}
        if "token_budget" in self.limits:
            config = self.limits["token_budget"]
            result["token_measure"] = "Full rendered messages estimate; reservations are not provider-reported usage."
            result["remaining_token_budget"] = {
                "input_tokens": config["max_total_input_tokens"] - self._token_spent["input"],
                "output_tokens": config["max_total_output_tokens"] - self._token_spent["output"],
                "stages": {key: {
                    "calls": stage["max_calls"] - self._stage_spent.get(key, {}).get("calls", 0),
                    "input_tokens": stage["max_total_input_tokens"] - self._stage_spent.get(key, {}).get("input", 0),
                    "output_tokens": stage["max_total_output_tokens"] - self._stage_spent.get(key, {}).get("output", 0),
                } for key, stage in config["stages"].items()}}
        return result

    def _render(self, prompt_id, inputs):
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
        return messages, values, schema_id

    def _inspect(self, prompt_id, messages):
        count = len(_json(messages))
        try:
            estimated = self._count_tokens(copy.deepcopy(messages))
        except Exception as exc:
            raise DomainError("invalid_model_counter", "Token counter failed before dispatch.",
                              {"error_type": type(exc).__name__}) from None
        if type(estimated) is not int or estimated < 0:
            raise DomainError("invalid_model_counter", "Token counter must return a nonnegative integer.")
        config = self.limits.get("token_budget")
        stage = config["stages"].get(prompt_id) if config else None
        cap = min(self.limits["max_output_tokens"], stage["max_output_tokens"]) if stage else self.limits["max_output_tokens"]
        reason = None
        checks = [("global", "calls", self.calls, 1, self.limits["max_calls"]),
                  ("request", "input_chars", 0, count, self.limits["max_input_chars"]),
                  ("global", "input_chars", self.input_chars, count, self.limits["max_total_input_chars"])]
        if config:
            if self._token_overrun is not None:
                reason = {"scope": "global", "dimension": "previous_overrun", "original": copy.deepcopy(self._token_overrun)}
            elif stage is None:
                reason = {"scope": "stage", "dimension": "unconfigured_stage", "prompt_id": prompt_id}
            else:
                spent = self._stage_spent.get(prompt_id, {"calls": 0, "input": 0, "output": 0})
                checks += [("request", "input_tokens", 0, estimated, config["max_input_tokens"]),
                           ("global", "input_tokens", self._token_spent["input"], estimated, config["max_total_input_tokens"]),
                           ("global", "output_tokens", self._token_spent["output"], cap, config["max_total_output_tokens"]),
                           ("stage", "calls", spent["calls"], 1, stage["max_calls"]),
                           ("stage_request", "input_tokens", 0, estimated, stage["max_input_tokens"]),
                           ("stage", "input_tokens", spent["input"], estimated, stage["max_total_input_tokens"]),
                           ("stage", "output_tokens", spent["output"], cap, stage["max_total_output_tokens"])]
                if cap == 0:
                    reason = {"scope": "stage_request", "dimension": "output_tokens", "limit": 0}
        if reason is None:
            for scope, dimension, consumed, requested, maximum in checks:
                if consumed + requested > maximum:
                    reason = {"scope": scope, "dimension": dimension, "consumed": consumed,
                              "requested": requested, "limit": maximum, "prompt_id": prompt_id}
                    break
        return {"fits": reason is None, "estimated_input_tokens": estimated, "effective_output_cap": cap,
                "input_chars": count, "messages_hash": digest(messages), "blocking_reason": reason,
                "budget": None if not config else {
                    "counter_id": config["counter_id"], "count_kind": config["count_kind"],
                    "remaining": self._visible_limits()["remaining_token_budget"]}}

    def preview(self, prompt_id, inputs):
        """Inspect the same complete render used by generate; never reserve or invoke."""
        with self._budget_lock:
            messages, _, _ = self._render(prompt_id, inputs)
            return self._inspect(prompt_id, messages)

    def _reserve(self, prompt_id, inspected):
        config = self.limits.get("token_budget")
        if config is None:
            return None
        incoming, outgoing = inspected["estimated_input_tokens"], inspected["effective_output_cap"]
        spent = self._stage_spent.setdefault(prompt_id, {"calls": 0, "input": 0, "output": 0})
        self._token_spent["input"] += incoming
        self._token_spent["output"] += outgoing
        spent["calls"] += 1
        spent["input"] += incoming
        spent["output"] += outgoing
        return {"counter_id": config["counter_id"], "count_kind": config["count_kind"], "stage": prompt_id,
                "estimated_input_tokens": incoming, "reserved_input_tokens": incoming,
                "reserved_output_tokens": outgoing, "input_debit": incoming, "output_debit": outgoing,
                "debit_basis": {"input": "reservation", "output": "reservation"},
                "budget_status": "reserved_unknown", "messages_hash": inspected["messages_hash"]}

    def _settle(self, entry):
        if "budget" not in entry:
            return None
        with self._budget_lock:
            record = entry["budget"]
            config = self.limits["token_budget"]
            stage = config["stages"][entry["prompt_id"]]
            spent = self._stage_spent[entry["prompt_id"]]
            for side in ("input", "output"):
                actual = entry[side + "_tokens"]
                if actual is not None:
                    difference = actual - record[side + "_debit"]
                    self._token_spent[side] += difference
                    spent[side] += difference
                    record[side + "_debit"] = actual
                    record["debit_basis"][side] = "provider_reported"
            checks = [("request", "input_tokens", record["input_debit"], config["max_input_tokens"]),
                      ("stage_request", "input_tokens", record["input_debit"], stage["max_input_tokens"]),
                      ("request", "output_tokens", record["output_debit"], record["reserved_output_tokens"]),
                      ("global", "input_tokens", self._token_spent["input"], config["max_total_input_tokens"]),
                      ("global", "output_tokens", self._token_spent["output"], config["max_total_output_tokens"]),
                      ("stage", "input_tokens", spent["input"], stage["max_total_input_tokens"]),
                      ("stage", "output_tokens", spent["output"], stage["max_total_output_tokens"])]
            for scope, dimension, actual, maximum in checks:
                if actual > maximum:
                    reason = {"scope": scope, "dimension": dimension, "actual": actual, "limit": maximum,
                              "prompt_id": entry["prompt_id"]}
                    record["budget_status"] = "overrun"
                    self._token_overrun = reason
                    return reason
            record["budget_status"] = "settled" if all(
                value == "provider_reported" for value in record["debit_basis"].values()) else "reserved_unknown"
            return None

    def generate(self, prompt_id, inputs, *, check=None):
        """Run optional pure semantic validation inside the same finite repair loop.

        ``check`` must not persist changes or execute a candidate. It receives a
        copy; its DomainError is repair feedback, never an extra retry allowance.
        """
        if check is not None and not callable(check):
            raise DomainError("invalid_model_check", "Semantic check must be a pure callable or None.")
        with self._budget_lock:
            messages, values, schema_id = self._render(prompt_id, inputs)
        usage, attempts = [], []

        def fail(code, message, **details):
            raise DomainError(code, message, {"prompt_id": prompt_id, "usage": copy.deepcopy(usage),
                "attempts": copy.deepcopy(attempts), "calls_consumed": self.calls,
                "input_chars_consumed": self.input_chars, **details})

        for repair in range(self.limits["max_format_repairs"] + 1):
            with self._budget_lock:
                try:
                    inspected = self._inspect(prompt_id, messages)
                except DomainError as exc:
                    fail(exc.code, exc.message, **exc.details)
                count = inspected["input_chars"]
                if not inspected["fits"]:
                    fail("model_budget_exhausted", "Call or input/output budget exhausted before the next attempt.",
                         requested_input_chars=count, limits=copy.deepcopy(self.limits), preview=inspected)
                self.calls += 1
                self.input_chars += count
                budget = self._reserve(prompt_id, inspected)
            started = time.monotonic()
            entry = {"usage_id": new_id("modelcall"), "prompt_id": prompt_id,
                     "attempt": repair + 1, "input_chars": count, "output_chars": None,
                     "input_tokens": None, "output_tokens": None, "total_tokens": None,
                     "monetary_cost": None, "currency": None, "price_version": None,
                     "measurement": "missing", "model": None, "request_id": None,
                     "elapsed_seconds": None, "status": "attempted"}
            if budget is not None:
                entry["budget"] = budget
            usage.append(entry)
            try:
                response = self.invoke({"prompt_id": prompt_id, "messages": copy.deepcopy(messages),
                                        "max_output_tokens": inspected["effective_output_cap"]})
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
                # Fees belong to the transport envelope, never the model's JSON draft.
                # Missing prices stay unknown; token counts are not an implicit quote.
                fee = normalize_usage_measurements({key: reported.get(key) for key in ("monetary_cost", "currency")})
                for key in ("monetary_cost", "currency"):
                    entry[key] = fee[key]
                for diagnostic in fee["diagnostics"]:
                    original = diagnostic["received"]
                    diagnostics.append({"path": diagnostic["path"], "expected": diagnostic["reason"],
                        "reported_type": type(original).__name__,
                        "reported_value": repr(original) if type(original) in (int, float, bool) else "<invalid value>"})
                version = reported.get("price_version")
                if version is None or (isinstance(version, str) and version.strip()):
                    entry["price_version"] = version
                else:
                    diagnostics.append({"path": "usage.price_version", "expected": "nonempty string or null",
                                        "reported_type": type(version).__name__, "reported_value": "<invalid value>"})
                # Retain a JSON-safe diagnostic instead of poisoning the shared ledger
                # (NaN is not JSON, and fractional/bool token counts are not counts).
                response["usage"] = {key: entry[key] for key in ("input_tokens", "output_tokens", "total_tokens",
                                                               "monetary_cost", "currency", "price_version")}
                if diagnostics:
                    entry["usage_diagnostics"] = diagnostics
                if any(entry[key] is not None for key in ("input_tokens", "output_tokens", "total_tokens")):
                    entry["measurement"] = "partial" if diagnostics else "provider_reported"
            entry["model"] = response.get("model")
            entry["request_id"] = response.get("request_id")
            overrun = self._settle(entry)
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
            if overrun is not None:
                entry["status"] = "budget_overrun"
                fail("model_budget_exhausted", "Provider usage exceeded the declared token budget.", overrun=overrun)
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
                    "total_tokens": usage.get("total_tokens"),
                    **{key: usage[key] for key in ("monetary_cost", "currency", "price_version") if key in usage}}}
    return invoke
