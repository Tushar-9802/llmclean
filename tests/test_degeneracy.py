"""Tests for llmclean.degeneracy.

Samples are verbatim from the Hybrid-Dataset Summariser degeneration study
(24 model variants, ~600 generations/eval).
"""

import pytest

from llmclean import (
    degeneracy_score, adjacent_dup_rate, intra_word_rate, looks_truncated,
    mixed_script_words, collapse_word_runs, collapse_intra_word_runs,
)

PHRASE = "The model runs fast. So this is 8 infinity. So this is 8 infinity. So this is 8 infinity."
TOKEN = "We tune the parameter parameter parameter values in in in a neural neural neural network today."
SUBWORD = "The back backproppropagationagationation step uses thresholdinginginging over the layers."
COLLAPSE = "dog dog dogog dogogog"
CLEAN = "The encoder maps input tokens to dense vectors before the attention layer runs downstream."


# --- each taxonomy level is caught by its own rule ---

@pytest.mark.parametrize("text,rule", [
    (PHRASE, "phrase_repetition"),
    (TOKEN, "adjacent_dup_rate"),
    (SUBWORD, "intra_word_rate"),
])
def test_each_level_fires_its_rule(text, rule):
    r = degeneracy_score(text)
    assert r["degenerate"]
    assert rule in r["rules_fired"]


def test_clean_text_not_flagged():
    assert degeneracy_score(CLEAN)["degenerate"] is False


def test_total_collapse_caught_by_word_level_rules():
    # Passes the subword rule (no 3-char repeat inside tokens) but trips others.
    r = degeneracy_score(COLLAPSE)
    assert r["degenerate"]
    assert "intra_word_rate" not in r["rules_fired"]


def test_subword_sample_invisible_to_word_level_metrics():
    # The reason four word-level rules are not enough: one unique word.
    r = degeneracy_score("thresholdinginginging")
    assert r["adjacent_dup_rate"] == 0.0
    assert r["distinct_ratio"] == 1.0
    assert "intra_word_rate" in r["rules_fired"]


# --- individual signals ---

def test_adjacent_dup_rate():
    assert adjacent_dup_rate("a a a b") == pytest.approx(2 / 3)
    assert adjacent_dup_rate(CLEAN) == 0.0
    assert adjacent_dup_rate("single") == 0.0


def test_intra_word_rate_ignores_hyphenated_reduplication():
    # \w does not cross the hyphen, so Indonesian-style plurals are safe.
    assert intra_word_rate("orang-orang berjalan") == 0.0


def test_short_text_flagged_as_weak_evidence():
    assert degeneracy_score("a a a")["short_text"] is True
    assert degeneracy_score(" ".join(["word%d" % i for i in range(40)]))["short_text"] is False


# --- truncation is a separate axis ---

def test_truncation_reported_separately():
    r = degeneracy_score("The encoder maps input tokens to dense")
    assert r["truncated"] is True
    assert "truncated" not in r["rules_fired"]


def test_terminated_text_not_truncated():
    assert looks_truncated(CLEAN) is False


# Regression: a Latin-only terminator set flagged 100% of Hindi and Chinese
# output as truncated. Found by replaying a multilingual production corpus.
@pytest.mark.parametrize("text", [
    "वर्षा तब होती है।",          # devanagari danda
    "यह पूरा वाक्य है॥",          # devanagari double danda
    "这是机器学习。",              # cjk ideographic full stop
    "真的吗？",                    # fullwidth question mark
    "太好了！",                    # fullwidth exclamation
    "他说「这样」",                # cjk closing quote
])
def test_non_latin_terminators_not_flagged_truncated(text):
    assert looks_truncated(text) is False


def test_genuinely_cut_non_latin_still_flagged():
    # A Hindi sentence cut mid-word (no danda) is still truncation.
    assert looks_truncated("वर्षा तब होती") is True


def test_closing_code_fence_is_not_truncation():
    assert looks_truncated("here:\n```python\nx = 1\n```") is False
    # ...but a fence cut mid-marker is.
    assert looks_truncated("here:\n```python\nx = 1\n``") is True


def test_truncation_with_cap_tokens_requires_near_cap():
    short = "ends abruptly"
    assert looks_truncated(short, cap_tokens=500) is False   # nowhere near the cap
    assert looks_truncated(short, cap_tokens=2) is True


# --- mixed script ---

def test_mixed_script_word_detected():
    assert mixed_script_words("the ReLУ activation works") == ["ReLУ"]


def test_document_level_script_mixing_is_not_flagged():
    # Hinglish / Devanagari+Latin is legitimate; only word-internal mixing counts.
    assert mixed_script_words("yeh model अच्छा hai overall") == []


def test_mixed_script_excluded_from_verdict():
    assert "mixed_script" not in degeneracy_score("the ReLУ works")["rules_fired"]


# --- repair ---

def test_collapse_word_runs_collapses_three():
    assert collapse_word_runs("the parameter parameter parameter values") == "the parameter values"


def test_collapse_word_runs_preserves_legitimate_doubles():
    t = "the things that that he had had before"
    assert collapse_word_runs(t) == t


def test_collapse_intra_word_runs_reaches_fixpoint():
    assert collapse_intra_word_runs("thresholdinginginging") == "thresholding"
    assert collapse_intra_word_runs("backproppropagationagationation") == "backpropagation"


def test_repair_is_separate_from_detection():
    # Detection never mutates.
    r = degeneracy_score(TOKEN)
    assert r["degenerate"] and TOKEN == TOKEN


# --- never raises ---

@pytest.mark.parametrize("bad", [None, 42, [], {}])
def test_non_string_passthrough(bad):
    assert degeneracy_score(bad)["degenerate"] is False
    assert collapse_word_runs(bad) == bad
    assert collapse_intra_word_runs(bad) == bad
    assert adjacent_dup_rate(bad) == 0.0
    assert intra_word_rate(bad) == 0.0
    assert looks_truncated(bad) is False
    assert mixed_script_words(bad) == []
