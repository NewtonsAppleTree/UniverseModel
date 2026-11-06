"""Strict configuration from JSON to existing frozen dataclasses; no formula interpreter."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import fields, is_dataclass
from math import isfinite
from pathlib import Path
from types import UnionType
from typing import Literal, TypeVar, Union, get_args, get_origin, get_type_hints

from contracts.versions.json_codec import parse_json


T = TypeVar("T")  # Resolved producer parameter type; no physical unit.


# Apply explicit dotted overrides to a copied tree; mappings merge by path, sequences replace wholesale.
def apply_overrides(values: Mapping[str, object], overrides: Mapping[str, object]) -> dict[str, object]:
    result = deepcopy(dict(values))
    for path, value in overrides.items():
        if type(path) is not str or any(not part for part in path.split(".")):
            raise ValueError("override path must contain nonempty dot-separated fields")
        parts = path.split(".")
        target = result
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            if type(target[part]) is not dict:
                raise ValueError(f"{path}: cannot traverse a non-object field")
            target = target[part]
        target[parts[-1]] = deepcopy(value)
    return result


# Convert declared scalars/tuples/unions/nested dataclasses; never coerce bool to count or string to number.
def _convert(annotation: object, value: object, path: str) -> object:
    origin, arguments = get_origin(annotation), get_args(annotation)
    if isinstance(annotation, type) and is_dataclass(annotation):
        return resolve_dataclass(annotation, value, _path=path)
    if origin in (Union, UnionType):
        for option in arguments:
            try:
                return _convert(option, value, path)
            except (TypeError, ValueError):
                pass
        raise TypeError(f"{path}: value does not match {annotation}")
    if origin is Literal:
        if any(type(value) is type(option) and value == option for option in arguments):
            return value
        raise ValueError(f"{path}: expected one of {arguments}")
    if origin is tuple:
        if type(value) not in (list, tuple):
            raise TypeError(f"{path}: expected a JSON array")
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return tuple(_convert(arguments[0], item, f"{path}[{i}]") for i, item in enumerate(value))
        if len(value) != len(arguments):
            raise ValueError(f"{path}: expected {len(arguments)} elements")
        return tuple(_convert(kind, item, f"{path}[{i}]")
                     for i, (kind, item) in enumerate(zip(arguments, value)))
    if annotation is float and type(value) in (int, float):
        try:
            result = float(value)
        except OverflowError as exc:
            raise ValueError(f"{path}: number exceeds binary64 range") from exc
        if not isfinite(result):
            raise ValueError(f"{path}: number must be finite")
        return result
    if annotation in (str, int, bool, type(None)) and type(value) is annotation:
        return value
    raise TypeError(f"{path}: expected {annotation}, got {type(value).__name__}")


# Resolve declared init fields only, then run producer __post_init__; derived fields cannot be overridden.
def resolve_dataclass(params_type: type[T], values: Mapping[str, object], *,
                      overrides: Mapping[str, object] | None = None, _path: str = "configuration") -> T:
    if not isinstance(params_type, type) or not is_dataclass(params_type) or not params_type.__dataclass_params__.frozen:
        raise TypeError("configuration type must be a frozen dataclass")
    if not isinstance(values, Mapping) or any(type(key) is not str for key in values):
        raise TypeError(f"{_path}: expected an object with string keys")
    values = apply_overrides(values, overrides) if overrides is not None else dict(values)
    declarations = {field.name: field for field in fields(params_type) if field.init}
    unknown = set(values) - set(declarations)
    if unknown:
        raise ValueError(f"{_path}: unknown or derived field(s): {', '.join(sorted(unknown))}")
    hints = get_type_hints(params_type)
    converted = {key: _convert(hints[key], value, f"{_path}.{key}") for key, value in values.items()}
    try:
        return params_type(**converted)
    except (TypeError, ValueError) as exc:
        raise type(exc)(f"{_path}: {exc}") from exc


# Load a UTF-8 JSON object, apply invocation overrides, and construct the same producer-owned parameters.
def load_config(params_type: type[T], path: str | Path, *, overrides: Mapping[str, object] | None = None) -> T:
    values = parse_json(Path(path).read_text(encoding="utf-8-sig"))
    return resolve_dataclass(params_type, values, overrides=overrides)
