"""Versioned JSON snapshots; identity is SHA-256 over canonical UTF-8 bytes."""

from dataclasses import fields, is_dataclass
from hashlib import sha256
import json
from math import isfinite
from collections.abc import Mapping


# Project dataclasses and JSON containers to values; reject ambiguous keys and nonfinite numbers.
def _json_value(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise TypeError("JSON object keys must be strings")
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float and isfinite(value):
        return value
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


# Canonical JSON v1: sorted string keys, compact separators, UTF-8, finite numbers; 1 differs from 1.0.
def canonical_json(value: object) -> str:
    return json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


# Content identity H=SHA256(canonical_json(value).encode('utf-8')); excludes filename and wall time.
def content_hash(value: object) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


# Duplicate keys cannot silently select a winning parameter value.
def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


# JSON has no NaN/Infinity literal; reject Python's permissive parser extensions.
def _invalid_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON number: {value}")


# Decode strict JSON; round-trip validation also rejects numeric overflow such as 1e999.
def parse_json(source: str) -> object:
    value = json.loads(source, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    _json_value(value)
    return value
