"""Minimal JSON-Schema-subset validator shared by the fake and provider adapters.

Supports exactly the keywords Plan 4's action-proposal schemas need. Anything
outside the subset raises UnsupportedSchemaError — loud, not silent (spec:
"Structured output, schema validator" section).
"""

from collections.abc import Mapping
from typing import Any

from ai.models.errors import ModelInvalidResponseError, UnsupportedSchemaError

_SUPPORTED_KEYWORDS = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "enum",
    "items",
    "minimum",
    "maximum",
}

_TYPE_CHECKS: dict[str, Any] = {
    "object": lambda d: isinstance(d, dict),
    "string": lambda d: isinstance(d, str),
    "number": lambda d: isinstance(d, (int, float)) and not isinstance(d, bool),
    "integer": lambda d: isinstance(d, int) and not isinstance(d, bool),
    "boolean": lambda d: isinstance(d, bool),
    "array": lambda d: isinstance(d, list),
}


def validate_against_schema(data: Any, schema: Mapping[str, Any]) -> None:
    """Validate data against the supported JSON-Schema subset.

    Raises ModelInvalidResponseError with a path-precise message, or
    UnsupportedSchemaError when the schema uses keywords outside the subset.
    """
    _reject_unsupported(schema)
    _validate(data, schema, "data")


def _reject_unsupported(schema: Mapping[str, Any]) -> None:
    unknown = set(schema) - _SUPPORTED_KEYWORDS
    if unknown:
        raise UnsupportedSchemaError(
            f"unsupported schema keywords: {', '.join(sorted(unknown))}"
        )
    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        for child in properties.values():
            if isinstance(child, Mapping):
                _reject_unsupported(child)
    items = schema.get("items")
    if isinstance(items, Mapping):
        _reject_unsupported(items)


def _validate(data: Any, schema: Mapping[str, Any], path: str) -> None:
    expected = schema.get("type")
    if expected is not None:
        _check_type(data, expected, path)
    if "enum" in schema:
        allowed = schema["enum"]
        if data not in allowed:
            raise ModelInvalidResponseError(f"{path}: {data!r} is not one of {allowed!r}")
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if "minimum" in schema and data < schema["minimum"]:
            raise ModelInvalidResponseError(
                f"{path}: {data} is less than minimum {schema['minimum']}"
            )
        if "maximum" in schema and data > schema["maximum"]:
            raise ModelInvalidResponseError(
                f"{path}: {data} is greater than maximum {schema['maximum']}"
            )
    if expected == "object" or "properties" in schema:
        _validate_object(data, schema, path)
    if expected == "array" or "items" in schema:
        _validate_array(data, schema, path)


def _check_type(data: Any, expected: str, path: str) -> None:
    check = _TYPE_CHECKS.get(expected)
    if check is None:
        raise UnsupportedSchemaError(f"unsupported schema type: {expected!r}")
    if not check(data):
        raise ModelInvalidResponseError(
            f"{path}: expected {expected}, got {type(data).__name__}"
        )


def _validate_object(data: Any, schema: Mapping[str, Any], path: str) -> None:
    if not isinstance(data, dict):
        return  # type mismatch already reported by _check_type
    for name in schema.get("required", []):
        if name not in data:
            raise ModelInvalidResponseError(f"{path}.{name}: required field is missing")
    properties = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        extras = set(data) - set(properties)
        if extras:
            raise ModelInvalidResponseError(
                f"{path}: unexpected field(s) {', '.join(sorted(extras))}"
            )
    for name, value in data.items():
        if name in properties and isinstance(properties[name], Mapping):
            _validate(value, properties[name], f"{path}.{name}")


def _validate_array(data: Any, schema: Mapping[str, Any], path: str) -> None:
    if not isinstance(data, list):
        return
    items = schema.get("items")
    if isinstance(items, Mapping):
        for index, value in enumerate(data):
            _validate(value, items, f"{path}[{index}]")
