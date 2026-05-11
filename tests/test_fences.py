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


# ---------------------------------------------------------------------------
# Line-ending robustness
# ---------------------------------------------------------------------------
# LLM output captured from any Windows client typically has CRLF (\r\n) line
# endings. Without explicit support, the open/close fence regexes (which use
# [ \t]*$ as the trailing anchor) don't tolerate a \r before \n, and the
# function silently strips the WRONG fence — preserving the opener as content
# and dropping the closer. See _probe_crlf.py for the original diagnosis.

def test_crlf_line_endings_equivalent_to_lf():
    """A CRLF-fenced block should clean to the same result as an LF-fenced block."""
    lf   = "```json\n{\"a\":1}\n```"
    crlf = "```json\r\n{\"a\":1}\r\n```"
    # Content equality after stripping out \r so the test isn't sensitive to
    # whether the fix normalizes line endings or preserves them.
    assert strip_fences(crlf).replace("\r", "") == strip_fences(lf)


def test_crlf_mixed_with_lf():
    """Mixed CRLF (e.g., copy-pasted content) should still strip correctly."""
    mixed = "```json\n{\"a\":1}\r\n```"
    result = strip_fences(mixed).replace("\r", "")
    assert result == '{"a":1}'


def test_crlf_unclosed_fence():
    """Unclosed CRLF fence: drop opener, keep content (matching the LF behavior)."""
    crlf = "```python\r\nprint('hi')"
    result = strip_fences(crlf).replace("\r", "")
    assert "print('hi')" in result
    assert "```" not in result


# ---------------------------------------------------------------------------
# CommonMark fence-length rules
# ---------------------------------------------------------------------------
# Spec: a closing fence must be at least as long as the opening fence.
#   - open `+`+ `+ → close must be 3+ backticks
#   - open ````+   → close must be 4+ backticks
# This lets users embed lower-length fences inside longer ones without
# accidentally terminating the outer block.

def test_close_longer_than_open_is_valid():
    """Open=3, close=5 → still a valid close (>= rule). Inner content extracted."""
    text = "```\ncode\n`````"
    result = strip_fences(text)
    assert "code" in result
    assert "```" not in result


def test_close_shorter_than_open_does_not_close():
    """Open=4, close=3 → 3 backticks must NOT close a 4-backtick fence. The
    short trailing ``` is treated as content; the actual fence is unclosed."""
    text = "````\ncode containing ``` inside\n````"
    result = strip_fences(text)
    # The genuine close (4 backticks) IS valid; inner content should appear.
    assert "code containing ``` inside" in result
    # And the outer 4-backtick fences themselves are gone.
    assert "````" not in result


def test_mixed_fence_types_both_stripped_aggressively():
    """Backtick open + tilde line — the tilde does NOT close the backtick
    fence (CommonMark: closer must match opener type). However, on the next
    pass the tilde is recognized as its own unclosed opener and is also
    stripped. Net effect: BOTH fence-shaped lines removed, content preserved.

    This is more aggressive than strict CommonMark (which would preserve the
    tilde line as content of an unclosed block) but matches llmclean's stated
    mandate: clean ALL fence-shaped artifacts. Characterization test —
    locks the aggressive interpretation in place."""
    text = "```python\nprint('hi')\n~~~"
    result = strip_fences(text)
    assert "print('hi')" in result
    assert "```" not in result
    assert "~~~" not in result


# ---------------------------------------------------------------------------
# Idempotency (a property test)
# ---------------------------------------------------------------------------
# strip_fences(strip_fences(x)) == strip_fences(x) — applying the cleaner
# twice must equal applying it once. This is a structural invariant that any
# pipeline composing `clean(clean(x))` (e.g., a retry loop, a defensive
# wrap-and-rewrap) silently depends on. A future "improvement" that breaks
# this would silently corrupt outputs.

@pytest.mark.parametrize("text", [
    "no fences here",
    "```json\n{\"a\":1}\n```",
    "prose\n```python\nx=1\n```\nmore prose\n```py\ny=2\n```",
    "```\nfoo\n```\n```\nbar\n```",
    "unfenced\n~~~\nfoo\n~~~\nmore",
    "```python\nunclosed",
    "",
])
def test_strip_fences_is_idempotent(text):
    once = strip_fences(text)
    twice = strip_fences(once)
    assert once == twice, (
        f"Not idempotent.\nonce ={once!r}\ntwice={twice!r}"
    )


# ---------------------------------------------------------------------------
# Characterizing the known trade-off — the lone-language-tag false positive
# ---------------------------------------------------------------------------
# When a user's actual content is just a known language name on its own line
# (e.g., model answered the question "what language?" with one word inside
# a code block), _LONE_LANG_TAG_RE strips it. This is a deliberate trade-off
# (see the comment on _LONE_LANG_TAG_RE) and the test locks the behavior in
# so a future "fix" that drops the language-tag cleanup doesn't silently
# regress fence cleanliness on more common inputs.

def test_lone_language_word_as_content_gets_stripped():
    """Known trade-off: a single-word answer that happens to be a language
    name will be removed. Documented limitation, not a bug to fix."""
    text = "```\njson\n```"
    result = strip_fences(text)
    # The 'json' content disappears entirely.
    assert result == ""
    # If you NEED to preserve such content, don't use strip_fences for it,
    # OR pre-process to prefix the content with a non-removable token.


# ---------------------------------------------------------------------------
# BOM handling — symmetric with enforce_json
# ---------------------------------------------------------------------------

def test_bom_before_fence_is_stripped():
    """A BOM (U+FEFF) right before the opening fence would otherwise break
    the `^` anchor on _OPEN_FENCE_RE (the line wouldn't start with the
    fence char). strip_fences handles it up-front."""
    text = "﻿" + "```json\n{\"a\": 1}\n```"
    result = strip_fences(text)
    assert "```" not in result
    assert '"a"' in result
