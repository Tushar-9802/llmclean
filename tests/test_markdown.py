"""Tests for llmclean.markdown.strip_markdown.

The REAL_GEMMA fixture is a verbatim capture from gemma4:e4b-it-q4_K_M via
dev/probe_generative.py (the "explain photosynthesis with headers and bullets"
prompt) — markdown was the most common output trait across the local baseline,
so this is validated against genuine model output, not only synthetic shapes.
"""

from llmclean import strip_markdown


# ---------------------------------------------------------------------------
# Synthetic unit coverage
# ---------------------------------------------------------------------------

def test_atx_header_flattened():
    assert strip_markdown("# Title\n\nbody") == "Title\n\nbody"


def test_bold_and_italic_unwrapped():
    assert strip_markdown("**bold** and *italic*") == "bold and italic"


def test_nested_emphasis_unwound():
    assert strip_markdown("***both***") == "both"


def test_inline_code_unwrapped():
    assert strip_markdown("call `func()` now") == "call func() now"


def test_links_keep_text_drop_url():
    assert strip_markdown("see [the docs](https://x.io/y)") == "see the docs"


def test_images_keep_alt():
    assert strip_markdown("![a diagram](img.png)") == "a diagram"


def test_bullets_stripped():
    assert strip_markdown("- one\n- two") == "one\ntwo"


def test_ordered_list_stripped():
    assert strip_markdown("1. first\n2. second") == "first\nsecond"


def test_blockquote_stripped():
    assert strip_markdown("> quoted line") == "quoted line"


def test_horizontal_rule_removed():
    assert strip_markdown("above\n\n---\n\nbelow") == "above\n\nbelow"


def test_snake_case_identifier_survives():
    # Underscore emphasis must not eat snake_case in prose.
    assert strip_markdown("set my_flag_value to true") == "set my_flag_value to true"


def test_hyphen_range_not_treated_as_bullet():
    # A '-' mid-line is not a list marker.
    assert strip_markdown("range a-b is fine") == "range a-b is fine"


def test_table_flattened():
    md = "| A | B |\n|---|---|\n| 1 | 2 |"
    out = strip_markdown(md)
    assert "|" not in out
    assert "A" in out and "B" in out and "1" in out and "2" in out


def test_code_fence_unwrapped():
    md = "Here:\n```python\nx = 1\n```"
    out = strip_markdown(md)
    assert "```" not in out
    assert "x = 1" in out


def test_non_string_passthrough():
    assert strip_markdown(None) is None


# ---------------------------------------------------------------------------
# REAL capture
# ---------------------------------------------------------------------------

REAL_GEMMA = (
    '# 🌿 What Is Photosynthesis?\n\n'
    'Photosynthesis is the fundamental biological process used by plants.\n\n'
    '*   **Definition:** The process of converting carbon dioxide into glucose.\n'
    '*   **Goal:** To create chemical energy stored in glucose.\n'
)


def test_real_gemma_markdown_flattened():
    out = strip_markdown(REAL_GEMMA)
    # Header hashes gone, bold markers gone, bullet markers gone.
    assert "#" not in out
    assert "**" not in out
    assert "*   " not in out
    # Readable content preserved.
    assert "What Is Photosynthesis?" in out
    assert "Definition:" in out
    assert "fundamental biological process" in out
