"""Tests for trim_repetition()"""

import pytest
from llmclean import trim_repetition


# ---------------------------------------------------------------------------
# No repetition — text must be returned unchanged
# ---------------------------------------------------------------------------

def test_no_repetition_unchanged():
    text = "The quick brown fox jumps over the lazy dog."
    assert trim_repetition(text) == text


def test_short_text_unchanged():
    text = "Hello!"
    assert trim_repetition(text) == text


def test_empty_string():
    assert trim_repetition("") == ""


# ---------------------------------------------------------------------------
# Exact sentence repetition
# ---------------------------------------------------------------------------

def test_exact_sentence_repeat_trimmed():
    text = (
        "Paris is the capital of France. "
        "It is known for the Eiffel Tower. "
        "It is known for the Eiffel Tower."
    )
    result = trim_repetition(text)
    assert result.count("It is known for the Eiffel Tower") == 1


def test_three_identical_sentences():
    base = "The answer is forty-two."
    text = "Here is the answer. " + (base + " ") * 3
    result = trim_repetition(text)
    assert result.count(base) <= 1


def test_repeated_sentence_at_end_only():
    # Repetition only at the tail — leading content untouched
    text = (
        "Introduction to the topic. "
        "First key point is very important. "
        "Second key point builds on that. "
        "Second key point builds on that."
    )
    result = trim_repetition(text)
    assert "Introduction to the topic" in result
    assert "First key point" in result
    assert result.count("Second key point builds on that") == 1


# ---------------------------------------------------------------------------
# Near-duplicate sentence detection
# ---------------------------------------------------------------------------

def test_near_duplicate_sentences():
    text = (
        "The model outputs a JSON object with the results. "
        "The model outputs a JSON structure containing the results."
    )
    # These are very similar but not identical — should be caught by Jaccard
    result = trim_repetition(text, similarity_threshold=0.6)
    # At least one of the near-dupe sentences should be removed
    assert len(result) < len(text)


def test_dissimilar_sentences_not_trimmed():
    text = (
        "The sky is blue. "
        "Quantum mechanics describes subatomic behavior."
    )
    assert trim_repetition(text) == text


# ---------------------------------------------------------------------------
# Paragraph-level repetition
# ---------------------------------------------------------------------------

def test_repeated_paragraph():
    para = "This is a complete paragraph with enough content to be meaningful."
    text = f"Opening paragraph with unique content.\n\n{para}\n\n{para}"
    result = trim_repetition(text)
    assert result.count(para) == 1
    assert "Opening paragraph" in result


def test_three_repeated_paragraphs():
    para = "Repeated paragraph that appears multiple times in the output."
    text = f"Unique intro.\n\n{para}\n\n{para}\n\n{para}"
    result = trim_repetition(text)
    assert result.count(para) <= 1


# ---------------------------------------------------------------------------
# N-gram repetition
# ---------------------------------------------------------------------------

def test_repeated_phrase_trimmed():
    # A phrase repeated 3+ times in the tail
    phrase = "in conclusion this is the final answer to the question"
    text = "Some intro content here. " + (phrase + " ") * 4
    result = trim_repetition(text)
    assert len(result) < len(text)


# ---------------------------------------------------------------------------
# Safety / edge cases
# ---------------------------------------------------------------------------

def test_non_string_input():
    assert trim_repetition(None) is None
    assert trim_repetition(42) == 42


def test_result_not_empty_on_repeated_text():
    # Even if everything repeats, should not return empty string
    text = "Hello. Hello. Hello."
    result = trim_repetition(text)
    assert result.strip() != ""


def test_similarity_threshold_respected():
    text = (
        "The weather today is sunny and warm. "
        "The weather today is sunny and warm."
    )
    # Strict threshold — identical so both methods should catch it
    result_strict = trim_repetition(text, similarity_threshold=0.99)
    assert result_strict.count("The weather today") == 1

    # Loose threshold — same result
    result_loose = trim_repetition(text, similarity_threshold=0.5)
    assert result_loose.count("The weather today") == 1