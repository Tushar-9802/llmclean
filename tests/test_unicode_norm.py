"""Tests for llmclean.unicode_norm — strip_invisibles & normalize_typography.

Scope note: a 5-model local baseline (llama/gemma/qwen/deepseek/mistral)
produced ZERO smart quotes, ellipsis chars, NBSP, ligatures, or zero-width
characters across 40 generations — even when prompted for them. That mess is a
frontier cloud-model trait, so these fixtures are SYNTHETIC by necessity: they
represent pasted ChatGPT/Claude/Gemini output, which is the real consumer of
these functions. (strip_markdown, by contrast, is tested against real local
captures because local models DO emit markdown heavily.)
"""

from llmclean import strip_invisibles, normalize_typography


# ---------------------------------------------------------------------------
# strip_invisibles
# ---------------------------------------------------------------------------

def test_zero_width_space_between_letters_removed():
    assert strip_invisibles("hel​lo") == "hello"


def test_bom_and_word_joiner_removed():
    assert strip_invisibles("﻿hi⁠there") == "hithere"


def test_bidi_marks_removed():
    assert strip_invisibles("a‮b‬c") == "abc"


def test_soft_hyphen_removed():
    assert strip_invisibles("co­operate") == "cooperate"


def test_ordinary_whitespace_preserved():
    assert strip_invisibles("a\tb\nc\rd") == "a\tb\nc\rd"


def test_control_chars_removed_but_not_whitespace():
    assert strip_invisibles("a\x00b\x07c") == "abc"


def test_emoji_zwj_sequence_preserved():
    # Man+ZWJ+Woman+ZWJ+Girl family emoji — the joiners must survive.
    family = "\U0001F468‍\U0001F469‍\U0001F467"
    assert strip_invisibles(family) == family


def test_zwj_adjacent_to_ascii_removed():
    # ZWJ injected between ASCII letters (a watermark trick) is removed.
    assert strip_invisibles("a‍b") == "ab"


def test_no_invisibles_unchanged():
    assert strip_invisibles("plain text") == "plain text"


def test_non_string_passthrough_invisibles():
    assert strip_invisibles(None) is None
    assert strip_invisibles(42) == 42


# ---------------------------------------------------------------------------
# normalize_typography
# ---------------------------------------------------------------------------

def test_smart_quotes_to_straight():
    assert normalize_typography("“hi” and ‘yo’") == '"hi" and \'yo\''


def test_dashes_to_hyphen():
    assert normalize_typography("a—b–c−d") == "a-b-c-d"


def test_ellipsis_char_to_dots():
    assert normalize_typography("wait…") == "wait..."


def test_nbsp_and_exotic_spaces_to_space():
    assert normalize_typography("a b c　d") == "a b c d"


def test_ligatures_expanded():
    assert normalize_typography("ﬁle ﬂow oﬃce") == "file flow office"


def test_snake_case_and_code_untouched():
    # No dashes/quotes here — underscores and ASCII must be left exactly alone.
    assert normalize_typography("my_var = func_name(x)") == "my_var = func_name(x)"


def test_categories_can_be_disabled():
    # Keep dashes, normalize everything else.
    out = normalize_typography("“hi”—x", dashes=False)
    assert out == '"hi"—x'


def test_fullwidth_off_by_default():
    assert normalize_typography("ｈｉ") == "ｈｉ"


def test_fullwidth_opt_in():
    # Fullwidth letters + punctuation + ideographic space.
    assert normalize_typography("ｈｉ！　", fullwidth=True) == "hi! "


def test_combined_realistic_cloud_paste():
    # The kind of string you get pasting ChatGPT output into a terminal.
    raw = "“It’s fine”—really… trust me."
    assert normalize_typography(raw) == '"It\'s fine"-really... trust me.'


def test_non_string_passthrough_typography():
    assert normalize_typography(None) is None
