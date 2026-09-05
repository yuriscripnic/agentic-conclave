import pytest

from ai.models.errors import ModelInvalidResponseError, UnsupportedSchemaError
from ai.models.schema import validate_against_schema

_OBJECT_SCHEMA = {
    "type": "object",
    "properties": {
        "action_type": {"type": "string", "enum": ["attack", "move"]},
        "parameters": {
            "type": "object",
            "properties": {"target_id": {"type": "string"}},
            "required": ["target_id"],
            "additionalProperties": False,
        },
        "count": {"type": "integer", "minimum": 1, "maximum": 10},
        "tags": {"type": "array", "items": {"type": "string"}},
        "verified": {"type": "boolean"},
        "ratio": {"type": "number"},
    },
    "required": ["action_type"],
    "additionalProperties": False,
}


def test_valid_object_passes() -> None:
    data = {
        "action_type": "attack",
        "parameters": {"target_id": "goblin-1"},
        "count": 3,
        "tags": ["melee"],
        "verified": True,
        "ratio": 0.5,
    }
    validate_against_schema(data, _OBJECT_SCHEMA)


def test_missing_required_field() -> None:
    with pytest.raises(ModelInvalidResponseError, match="action_type: required field is missing"):
        validate_against_schema({}, _OBJECT_SCHEMA)


def test_nested_path_in_error_message() -> None:
    data = {"action_type": "attack", "parameters": {"target_id": 3}}
    with pytest.raises(
        ModelInvalidResponseError, match="data.parameters.target_id: expected string, got int"
    ):
        validate_against_schema(data, _OBJECT_SCHEMA)


def test_enum_violation() -> None:
    with pytest.raises(ModelInvalidResponseError, match="is not one of"):
        validate_against_schema({"action_type": "flee"}, _OBJECT_SCHEMA)


def test_additional_properties_rejected() -> None:
    with pytest.raises(ModelInvalidResponseError, match="unexpected field"):
        validate_against_schema({"action_type": "attack", "extra": 1}, _OBJECT_SCHEMA)


def test_integer_bounds() -> None:
    with pytest.raises(ModelInvalidResponseError, match="less than minimum"):
        validate_against_schema({"action_type": "attack", "count": 0}, _OBJECT_SCHEMA)
    with pytest.raises(ModelInvalidResponseError, match="greater than maximum"):
        validate_against_schema({"action_type": "attack", "count": 11}, _OBJECT_SCHEMA)


def test_array_items_validated_with_index_path() -> None:
    data = {"action_type": "attack", "tags": ["ok", 5]}
    with pytest.raises(ModelInvalidResponseError, match=r"data\.tags\[1\]: expected string"):
        validate_against_schema(data, _OBJECT_SCHEMA)


def test_boolean_is_not_integer() -> None:
    with pytest.raises(ModelInvalidResponseError, match="expected integer, got bool"):
        validate_against_schema({"action_type": "attack", "count": True}, _OBJECT_SCHEMA)


def test_number_accepts_integer_value() -> None:
    validate_against_schema({"action_type": "attack", "ratio": 1}, _OBJECT_SCHEMA)


def test_unsupported_keyword_rejected() -> None:
    with pytest.raises(UnsupportedSchemaError, match="oneOf"):
        validate_against_schema({}, {"oneOf": []})


def test_unsupported_nested_keyword_rejected() -> None:
    schema = {"type": "object", "properties": {"x": {"type": "string", "pattern": "^a$"}}}
    with pytest.raises(UnsupportedSchemaError, match="pattern"):
        validate_against_schema({}, schema)
