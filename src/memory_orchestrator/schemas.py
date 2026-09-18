"""Packaged blueprint contracts and small, shared JSON primitives."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

from jsonschema import Draft202012Validator, FormatChecker


class DomainError(ValueError):
    """A machine-readable failure; callers retain code and detailed field paths."""

    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {} if details is None else details


def json_bytes(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DomainError("INVALID_JSON", "Value must be finite UTF-8 JSON", {"error": str(exc)}) from exc


def digest(value):
    """Hash raw UTF-8 text/bytes, or canonical JSON for structured values."""
    if isinstance(value, str):
        value = value.encode("utf-8")
    elif not isinstance(value, bytes):
        value = json_bytes(value)
    return hashlib.sha256(value).hexdigest()


def new_id(prefix):
    if not isinstance(prefix, str) or not prefix or not prefix.replace("_", "").isalnum():
        raise DomainError("INVALID_ARGUMENT", "ID prefix must be alphanumeric")
    return f"{prefix}_{uuid.uuid4().hex}"


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _bundle(filename):
    path = Path(__file__).with_name(filename)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DomainError("CONTRACT_UNAVAILABLE", f"Cannot read packaged {filename}",
                          {"path": str(path), "error": str(exc)}) from exc


def load_contracts():
    schema_bundle = _bundle("schemas.json")
    prompt_bundle = _bundle("prompts.json")
    if schema_bundle["source"] != prompt_bundle["source"]:
        raise DomainError("CONTRACT_SOURCE_MISMATCH", "Packaged schemas and prompts have different sources")
    return {**schema_bundle, "prompts": prompt_bundle["prompts"]}


def validate(schema_name, value):
    """Return independent JSON data, or all schema errors with precise paths."""
    schemas = _bundle("schemas.json")["schemas"]
    if schema_name not in schemas:
        raise DomainError("UNKNOWN_SCHEMA", f"Unknown schema: {schema_name}")
    copied = json.loads(json_bytes(value))
    validator = Draft202012Validator(schemas[schema_name], format_checker=FormatChecker())
    errors = []
    for error in validator.iter_errors(copied):
        path = "$" + "".join(f"[{part}]" if isinstance(part, int) else f".{part}"
                              for part in error.absolute_path)
        errors.append({"path": path, "message": error.message, "validator": error.validator})
    if errors:
        raise DomainError("SCHEMA_INVALID", f"Invalid {schema_name}", {"errors": errors})
    return deepcopy(copied)
