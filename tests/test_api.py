"""Tests for the three front doors: load_json, clean_text, check."""

import pytest

import llmclean
from llmclean import load_json, clean_text, check


# --- load_json ---

def test_load_json_returns_real_dict():
    assert load_json('{"a": 1}') == {"a": 1}


def test_load_json_through_fences_and_prose():
    raw = 'Sure! Here you go:\n```json\n{"ok": True, "n": [1,2,3,]}\n```\nHope that helps!'
    assert load_json(raw) == {"ok": True, "n": [1, 2, 3]}


def test_load_json_strips_reasoning_trace_first():
    # Braces inside the <think> block must not confuse extraction.
    raw = '<think>maybe {"wrong": 1} is right?</think>\n{"right": 2}'
    assert load_json(raw) == {"right": 2}


def test_load_json_returns_default_on_failure():
    assert load_json("no json here at all") is None
    assert load_json("nope", default={}) == {}


def test_load_json_handles_arrays():
    assert load_json("```json\n[1, 2, 3]\n```") == [1, 2, 3]


@pytest.mark.parametrize("bad", [None, 42, [], {}])
def test_load_json_non_string(bad):
    assert load_json(bad) is None


# --- clean_text ---

def test_clean_text_full_pipeline():
    raw = "<think>hmm</think>Sure! Here is the answer: # Title\n\n- **bold** point"
    out = clean_text(raw)
    assert "<think>" not in out
    assert "Sure!" not in out
    assert "#" not in out and "**" not in out
    assert "bold point" in out


def test_clean_text_normalizes_typography():
    assert clean_text("“hi”—there…") == '"hi"-there...'


def test_clean_text_strips_invisibles():
    assert clean_text("hel​lo") == "hello"


def test_clean_text_stages_can_be_disabled():
    out = clean_text("# Title", markdown=False)
    assert out.startswith("#")


def test_clean_text_repetition_off_by_default():
    # Silently trimming repetition would hide model damage; check() surfaces it.
    raw = "The answer is 42. This is final. This is final. This is final."
    assert clean_text(raw) == raw
    assert clean_text(raw, repetition=True) != raw


@pytest.mark.parametrize("bad", [None, 42])
def test_clean_text_non_string(bad):
    assert clean_text(bad) == bad


# --- check ---

def test_check_reports_without_modifying():
    raw = "We tune the parameter parameter parameter values today."
    r = check(raw)
    assert r["degenerate"] is True
    assert "adjacent_dup_rate" in r["rules_fired"]


def test_check_clean_text_not_flagged():
    assert check("The encoder maps input tokens to dense vectors downstream.")["degenerate"] is False


def test_check_passes_cap_tokens_through():
    assert check("ends abruptly", cap_tokens=2)["truncated"] is True


# --- the front doors are the advertised entry points ---

def test_front_doors_exported_first():
    assert llmclean.__all__[:3] == ["load_json", "clean_text", "check"]
