"""
repetition.py — detect and trim repetitive content at the end of LLM output.

LLMs sometimes loop: they repeat the same sentence, phrase, or paragraph
multiple times — especially near the end of a generation.  This module
trims that tail while preserving the legitimate content before it.

Detection strategies (applied in order, first match wins):
  1. Exact sentence repetition  — the same sentence appears 2+ times in a row
     at the tail of the text.
  2. Near-duplicate sentences   — sentences that are ≥ N% similar (Jaccard on
     word tokens) appear 2+ times in a row.
  3. N-gram phrase repetition   — a multi-word phrase of 4+ tokens repeats
     3+ times anywhere in the last quarter of the text.
  4. Paragraph-level repetition — same paragraph (≥ 20 chars) repeated 2+
     times at the end.

The function is conservative by design: it only trims from the *end* of the
text and requires repetition to be clearly back-to-back or densely clustered.
"""

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Tunables (all have sensible defaults)
# ---------------------------------------------------------------------------

# Minimum sentence length (chars) before we consider it for dedup
_MIN_SENTENCE_LEN = 12

# Jaccard similarity threshold to call two sentences "near-duplicates"
_JACCARD_THRESHOLD = 0.82

# Minimum n-gram size for phrase repetition detection
_NGRAM_SIZE = 5

# How many times an n-gram must repeat before we act
_NGRAM_MIN_REPEAT = 3

# Minimum paragraph length (chars) for paragraph-level dedup
_MIN_PARA_LEN = 20


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def trim_repetition(text: str, *, similarity_threshold: float = _JACCARD_THRESHOLD) -> str:
    """Detect and remove repetitive content from the tail of *text*.

    Only removes content from the *end* of the text.  If no repetition is
    detected the original text is returned unchanged.  Never raises.

    Parameters
    ----------
    text:
        Raw LLM output to clean.
    similarity_threshold:
        Jaccard similarity (0–1) above which two sentences are considered
        duplicates.  Default 0.82.  Lower = more aggressive trimming.

    Returns
    -------
    str
        Cleaned text with repetitive tail removed, or original if no
        repetition is found.
    """
    if not isinstance(text, str) or not text.strip():
        return text

    original = text
    try:
        result = _trim(text, similarity_threshold)
        return result if result.strip() else original
    except Exception:
        return original


# ---------------------------------------------------------------------------
# Core trimmer
# ---------------------------------------------------------------------------

def _trim(text: str, sim_threshold: float) -> str:
    strategies = [
        lambda t: _trim_exact_sentence_repeat(t),
        lambda t: _trim_near_duplicate_sentences(t, sim_threshold),
        lambda t: _trim_ngram_repeat(t),
        lambda t: _trim_paragraph_repeat(t),
    ]
    for strategy in strategies:
        cleaned = strategy(text)
        if cleaned != text:
            # Apply recursively — sometimes repetition is layered
            return _trim(cleaned, sim_threshold)
    return text


# ---------------------------------------------------------------------------
# Strategy 1: exact sentence repetition
# ---------------------------------------------------------------------------

def _trim_exact_sentence_repeat(text: str) -> str:
    """Remove consecutive duplicate sentences from the tail."""
    sentences = _split_sentences(text)
    if len(sentences) < 2:
        return text

    # Find the last run of 2+ identical sentences
    cut_idx = _find_repeat_run(sentences, key=lambda s: s.strip().lower())
    if cut_idx is None:
        return text

    return _rejoin_sentences(sentences[:cut_idx]).rstrip()


# ---------------------------------------------------------------------------
# Strategy 2: near-duplicate sentence detection
# ---------------------------------------------------------------------------

def _trim_near_duplicate_sentences(text: str, threshold: float) -> str:
    """Remove near-duplicate consecutive sentences from the tail."""
    sentences = _split_sentences(text)
    if len(sentences) < 2:
        return text

    cut_idx = _find_repeat_run(
        sentences,
        key=lambda s: frozenset(_tokenize(s)),
        similarity=lambda a, b: _jaccard(a, b) >= threshold,
    )
    if cut_idx is None:
        return text

    return _rejoin_sentences(sentences[:cut_idx]).rstrip()


# ---------------------------------------------------------------------------
# Strategy 3: n-gram phrase repetition
# ---------------------------------------------------------------------------

def _trim_ngram_repeat(text: str) -> str:
    """Detect a repeated multi-word phrase and trim from its second occurrence."""
    words = _tokenize(text)
    if len(words) < _NGRAM_SIZE * _NGRAM_MIN_REPEAT:
        return text

    # Only look in the last 75% of the word list to stay conservative
    search_start = len(words) // 4

    ngram_positions: dict[tuple, list[int]] = {}
    for i in range(search_start, len(words) - _NGRAM_SIZE + 1):
        ngram = tuple(words[i:i + _NGRAM_SIZE])
        ngram_positions.setdefault(ngram, []).append(i)

    # Find the n-gram with most repeats; trim before its second occurrence
    best: Optional[tuple] = None
    best_positions: list[int] = []
    for ngram, positions in ngram_positions.items():
        if len(positions) >= _NGRAM_MIN_REPEAT:
            if not best or positions[0] < best_positions[0]:
                best = ngram
                best_positions = positions

    if best is None:
        return text

    # Reconstruct text up to (but not including) the second occurrence
    cut_word_idx = best_positions[1]
    return _words_to_text_approx(text, words, cut_word_idx)


# ---------------------------------------------------------------------------
# Strategy 4: paragraph-level repetition
# ---------------------------------------------------------------------------

def _trim_paragraph_repeat(text: str) -> str:
    """Remove repeated paragraphs at the tail."""
    paras = [p.strip() for p in re.split(r"\n{2,}", text)]
    paras = [p for p in paras if len(p) >= _MIN_PARA_LEN]
    if len(paras) < 2:
        return text

    cut_idx = _find_repeat_run(paras, key=lambda p: p.lower())
    if cut_idx is None:
        return text

    # Rejoin paragraphs up to the cut point
    rejoined = "\n\n".join(paras[:cut_idx])
    return rejoined.rstrip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, keeping the delimiter."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p for p in parts if len(p.strip()) >= _MIN_SENTENCE_LEN]


def _rejoin_sentences(sentences: list[str]) -> str:
    return " ".join(sentences)


def _tokenize(text: str) -> list[str]:
    """Lowercase word tokens, no punctuation."""
    return re.findall(r"\b[a-z0-9]+\b", text.lower())


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def _find_repeat_run(items: list, *, key=None, similarity=None) -> Optional[int]:
    """Return the cut index: keep items[:cut], which preserves ONE copy of the
    repeated item and drops all subsequent duplicates.

    Scans from the end.  Returns None if no such run exists.
    ``key`` maps an item to a comparable value.
    ``similarity`` is an optional callable(key(a), key(b)) -> bool; if
    omitted, equality is used.
    """
    if not items:
        return None

    keys = [key(item) if key else item for item in items]
    eq = similarity if similarity else (lambda a, b: a == b)

    n = len(keys)
    # Walk backwards looking for a run of duplicates
    i = n - 1
    while i > 0:
        if eq(keys[i], keys[i - 1]):
            # Found a duplicate pair — find the start of this run
            run_start = i - 1
            while run_start > 0 and eq(keys[run_start], keys[run_start - 1]):
                run_start -= 1
            # Keep one copy: cut point is run_start + 1
            return run_start + 1
        i -= 1
    return None


def _words_to_text_approx(original: str, words: list[str], cut_word_idx: int) -> str:
    """Return original text truncated approximately at the *cut_word_idx*-th word."""
    # Find the character offset of the cut_word_idx-th word in the original
    pattern = re.compile(r"\b[a-z0-9]+\b", re.IGNORECASE)
    for i, m in enumerate(pattern.finditer(original)):
        if i == cut_word_idx:
            return original[:m.start()].rstrip()
    return original