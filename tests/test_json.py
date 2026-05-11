"""Tests for enforce_json()"""

import json
import pytest
from llmclean import enforce_json


def _is_valid_json(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Already-valid JSON
# ---------------------------------------------------------------------------

def test_already_valid_object():
    text = '{"key": "value"}'
    result = enforce_json(text)
    assert _is_valid_json(result)
    assert json.loads(result)["key"] == "value"


def test_already_valid_array():
    text = '[1, 2, 3]'
    result = enforce_json(text)
    assert _is_valid_json(result)
    assert json.loads(result) == [1, 2, 3]


# ---------------------------------------------------------------------------
# Fenced JSON
# ---------------------------------------------------------------------------

def test_json_in_fence():
    text = '```json\n{"name": "Alice"}\n```'
    result = enforce_json(text)
    assert _is_valid_json(result)
    assert json.loads(result)["name"] == "Alice"


def test_json_in_anonymous_fence():
    text = '```\n{"x": 42}\n```'
    result = enforce_json(text)
    assert _is_valid_json(result)


# ---------------------------------------------------------------------------
# Prose wrapping
# ---------------------------------------------------------------------------

def test_json_with_leading_prose():
    text = 'Sure! Here is your JSON:\n{"result": true}'
    result = enforce_json(text)
    assert _is_valid_json(result)


def test_json_with_trailing_prose():
    text = '{"result": true}\nHope that helps!'
    result = enforce_json(text)
    assert _is_valid_json(result)


def test_json_sandwiched_in_prose():
    text = 'Certainly! The data is {"items": [1,2,3]}. Let me know if you need more.'
    result = enforce_json(text)
    assert _is_valid_json(result)
    assert json.loads(result)["items"] == [1, 2, 3]


# ---------------------------------------------------------------------------
# Trailing commas
# ---------------------------------------------------------------------------

def test_trailing_comma_in_object():
    text = '{"a": 1, "b": 2,}'
    result = enforce_json(text)
    assert _is_valid_json(result)


def test_trailing_comma_in_array():
    text = '[1, 2, 3,]'
    result = enforce_json(text)
    assert _is_valid_json(result)


def test_trailing_comma_nested():
    text = '{"a": [1, 2,], "b": {"c": 3,},}'
    result = enforce_json(text)
    assert _is_valid_json(result)


# ---------------------------------------------------------------------------
# Unclosed brackets
# ---------------------------------------------------------------------------

def test_unclosed_object():
    text = '{"a": 1, "b": 2'
    result = enforce_json(text)
    assert _is_valid_json(result)


def test_unclosed_nested():
    text = '{"a": [1, 2'
    result = enforce_json(text)
    assert _is_valid_json(result)


# ---------------------------------------------------------------------------
# Unquoted keys
# ---------------------------------------------------------------------------

def test_unquoted_keys():
    text = '{name: "Alice", age: 30}'
    result = enforce_json(text)
    assert _is_valid_json(result)
    data = json.loads(result)
    assert data["name"] == "Alice"


# ---------------------------------------------------------------------------
# Combined issues
# ---------------------------------------------------------------------------

def test_fence_plus_trailing_comma():
    text = '```json\n{"a": 1,}\n```'
    result = enforce_json(text)
    assert _is_valid_json(result)


def test_prose_plus_fence_plus_trailing_comma():
    text = 'Here you go:\n```json\n{"items": [1, 2, 3,],}\n```\nDone!'
    result = enforce_json(text)
    assert _is_valid_json(result)


# ---------------------------------------------------------------------------
# Failure / safety
# ---------------------------------------------------------------------------

def test_completely_invalid_returns_original():
    text = "This is not JSON at all."
    result = enforce_json(text)
    assert result == text


def test_empty_string():
    result = enforce_json("")
    # Empty string is not valid JSON — should return unchanged
    assert result == ""


def test_non_string_input():
    assert enforce_json(None) is None
    assert enforce_json(42) == 42


def test_deeply_nested_valid():
    data = {"a": {"b": {"c": [1, 2, {"d": True}]}}}
    text = json.dumps(data)
    result = enforce_json(text)
    assert _is_valid_json(result)
    assert json.loads(result) == data


# ---------------------------------------------------------------------------
# Python literals (True / False / None / single quotes)
# ---------------------------------------------------------------------------

def test_python_true_false_none():
    text = '{"active": True, "deleted": False, "alias": None}'
    result = enforce_json(text)
    assert _is_valid_json(result)
    data = json.loads(result)
    assert data["active"] is True
    assert data["deleted"] is False
    assert data["alias"] is None


def test_python_literals_in_array():
    text = '[True, False, None, 42]'
    result = enforce_json(text)
    assert _is_valid_json(result)
    assert json.loads(result) == [True, False, None, 42]


def test_python_literals_mixed_with_other_issues():
    # Trailing comma + Python literals + fence
    text = '```json\n{"ok": True, "val": None,}\n```'
    result = enforce_json(text)
    assert _is_valid_json(result)
    data = json.loads(result)
    assert data["ok"] is True
    assert data["val"] is None


def test_single_quoted_keys_and_values():
    text = "{'name': 'Alice', 'age': 30}"
    result = enforce_json(text)
    assert _is_valid_json(result)
    data = json.loads(result)
    assert data["name"] == "Alice"


# ---------------------------------------------------------------------------
# BOM (U+FEFF) handling
# ---------------------------------------------------------------------------
# Some LLM client SDKs and any Windows file IO round-trip can prepend a UTF-8
# Byte Order Mark to the response. json.loads sees U+FEFF as "Unexpected
# character at position 0" and fails. Sakhi hit this in production logs;
# llmclean now strips it up-front. The original input is not mutated — only
# the working copy fed to the strategy pipeline.

def test_bom_stripped_from_object():
    text = "﻿" + '{"key": "value"}'
    result = enforce_json(text)
    assert _is_valid_json(result)
    assert json.loads(result)["key"] == "value"


def test_bom_stripped_from_fenced_json():
    text = "﻿" + '```json\n{"a": 1}\n```'
    result = enforce_json(text)
    assert _is_valid_json(result)
    assert json.loads(result)["a"] == 1


def test_bom_only_input_returns_unchanged():
    # Pure BOM, no JSON anywhere → fail gracefully, return original
    text = "﻿"
    result = enforce_json(text)
    # Function never raises; original or empty is acceptable.
    assert result in (text, "")


# ---------------------------------------------------------------------------
# Double-quote overrun collapse
# ---------------------------------------------------------------------------
# Models occasionally double the quotes around a value (e.g. from Python
# triple-string leaks: '"""{"foo": "bar"}"""'). The collapse pattern
# requires non-empty content between the doubled quotes, so legitimate
# empty strings ("") are never matched.

def test_double_quote_collapse_around_value():
    text = '{"key": ""value""}'
    result = enforce_json(text)
    assert _is_valid_json(result)
    assert json.loads(result)["key"] == "value"


def test_double_quote_collapse_around_key():
    text = '{""key"": "value"}'
    result = enforce_json(text)
    assert _is_valid_json(result)
    assert json.loads(result)["key"] == "value"


def test_double_quote_triple_overrun():
    # Triple quotes on both sides
    text = '{"""key""": """value"""}'
    result = enforce_json(text)
    assert _is_valid_json(result)
    assert json.loads(result)["key"] == "value"


def test_double_quote_legitimate_empty_string_preserved():
    """Critical: an empty-string value ("") must NOT be collapsed. The
    overrun regex requires content between the doubled quotes, so this is
    safe by construction. This test locks the safety in place."""
    text = '{"key": ""}'
    result = enforce_json(text)
    assert _is_valid_json(result)
    assert json.loads(result)["key"] == ""


def test_double_quote_legitimate_empty_string_in_array():
    text = '["a", "", "b"]'
    result = enforce_json(text)
    assert _is_valid_json(result)
    assert json.loads(result) == ["a", "", "b"]
