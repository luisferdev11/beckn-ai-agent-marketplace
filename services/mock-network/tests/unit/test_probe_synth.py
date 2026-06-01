"""Unit tests for input synthesis + output validation (Epic E1/E3)."""
from __future__ import annotations

from jsonschema import Draft202012Validator

from app.probe.synth import synthesize, synthesize_valid_input, validate_output


class TestSynthesize:
    def test_object_with_required_string(self):
        schema = {"type": "object", "properties": {"text": {"type": "string"}},
                  "required": ["text"]}
        out = synthesize(schema)
        assert isinstance(out, dict) and isinstance(out["text"], str)

    def test_honours_default(self):
        assert synthesize({"type": "string", "default": "hello"}) == "hello"

    def test_honours_enum(self):
        assert synthesize({"type": "string", "enum": ["a", "b"]}) == "a"

    def test_honours_examples(self):
        assert synthesize({"type": "object", "examples": [{"k": 1}]}) == {"k": 1}

    def test_nested_object(self):
        schema = {
            "type": "object",
            "properties": {
                "doc": {"type": "object",
                        "properties": {"body": {"type": "string"}},
                        "required": ["body"]},
            },
            "required": ["doc"],
        }
        out = synthesize(schema)
        assert isinstance(out["doc"]["body"], str)

    def test_array_min_items(self):
        out = synthesize({"type": "array", "items": {"type": "string"}, "minItems": 2})
        assert out == ["probe-sample", "probe-sample"]

    def test_integer_and_boolean(self):
        assert isinstance(synthesize({"type": "integer"}), int)
        assert isinstance(synthesize({"type": "boolean"}), bool)


class TestSynthesizeValidInput:
    def test_valid_schema_yields_valid_payload(self):
        schema = {"type": "object", "properties": {"text": {"type": "string"}},
                  "required": ["text"]}
        payload, errors = synthesize_valid_input(schema)
        assert errors == []
        # E1: the synthesised payload must pass jsonschema.validate.
        assert list(Draft202012Validator(schema).iter_errors(payload)) == []

    def test_complex_schema_validates(self):
        schema = {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "lang": {"type": "string", "enum": ["en", "hi"]},
                "max_words": {"type": "integer", "default": 100},
            },
            "required": ["text", "lang"],
        }
        payload, errors = synthesize_valid_input(schema)
        assert errors == []
        assert payload["lang"] in ("en", "hi")


class TestValidateOutput:
    def test_valid_output(self):
        schema = {"type": "object", "properties": {"summary": {"type": "string"}},
                  "required": ["summary"]}
        assert validate_output({"summary": "ok"}, schema) == []

    def test_invalid_output_reports_errors(self):
        schema = {"type": "object", "properties": {"summary": {"type": "string"}},
                  "required": ["summary"]}
        errs = validate_output({"wrong": 1}, schema)
        assert errs  # missing required 'summary'
