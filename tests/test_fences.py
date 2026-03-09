"""Tests for strip_fences()"""

import pytest
from llmclean import strip_fences


# ---------------------------------------------------------------------------
# Basic cases
# ---------------------------------------------------------------------------

def test_no_fence_returns_unchanged():
    text = "Hello, world!"
    assert strip_fences(text) == text


def test_simple_json_fence():
    text = "```json\n{\"key\": \"value\"}\n```"
    assert strip_fences(text) == '{"key": "value"}'


def test_simple_python_fence():
    text = "```python\nprint('hello')\n```"
    assert strip_fences(text) == "print('hello')"


def test_anonymous_fence():
    text = "```\nsome content\n```"
    assert strip_fences(text) == "some content"


def test_tilde_fence():
    text = "~~~python\nx = 1\n~~~"
    assert strip_fences(text) == "x = 1"


# ---------------------------------------------------------------------------
# Multiple fences
# ---------------------------------------------------------------------------

def test_multiple_fences_stripped():
    text = "```json\n{\"a\":1}\n```\n\nsome text\n\n```python\nx=2\n```"
    result = strip_fences(text)
    assert '{"a":1}' in result
    assert "x=2" in result
    assert "```" not in result


def test_back_to_back_fences():
    text = "```\nfirst\n```\n```\nsecond\n```"
    result = strip_fences(text)
    assert "first" in result
    assert "second" in result
    assert "```" not in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_fence_with_leading_whitespace():
    text = "   ```json\n{}\n```"
    assert "```" not in strip_fences(text)


def test_unclosed_fence():
    # Should drop the opening line and preserve the rest
    text = "```python\nprint('hi')"
    result = strip_fences(text)
    assert "print('hi')" in result
    assert "```" not in result


def test_empty_string():
    assert strip_fences("") == ""


def test_only_fence_markers():
    text = "```\n```"
    result = strip_fences(text)
    assert "```" not in result


def test_non_string_input():
    # Should return input unchanged, not crash
    assert strip_fences(None) is None
    assert strip_fences(123) == 123


def test_content_preserved_before_fence():
    text = "Here is the result:\n```json\n{\"x\":1}\n```"
    result = strip_fences(text)
    assert "Here is the result:" in result
    assert '{"x":1}' in result


def test_content_preserved_after_fence():
    text = "```json\n{\"x\":1}\n```\nHope that helps!"
    result = strip_fences(text)
    assert '{"x":1}' in result
    assert "Hope that helps!" in result


def test_four_backtick_fence():
    text = "````python\ncode here\n````"
    result = strip_fences(text)
    assert "code here" in result
    assert "````" not in result


def test_fence_with_multiline_content():
    text = "```\nline 1\nline 2\nline 3\n```"
    result = strip_fences(text)
    assert "line 1" in result
    assert "line 2" in result
    assert "line 3" in result


def test_nested_fences_all_stripped():
    # Outer fence contains inner fence markers
    text = "```\n```inner\ncode\n```\n```"
    result = strip_fences(text)
    assert "code" in result
    assert "```" not in result


def test_lone_language_tag_removed():
    # After fence stripping, a bare 'json' line should be cleaned up
    text = "```json\n{\"a\": 1}\n```"
    result = strip_fences(text)
    # The word 'json' on its own line should not appear
    lines = [l.strip() for l in result.splitlines()]
    assert "json" not in lines