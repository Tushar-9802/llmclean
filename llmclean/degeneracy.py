"""
degeneracy.py — detect (and optionally repair) degenerate LLM output.

Repetition happens at three levels, each a different bug:
  phrase  — clause loops; tail-concentrated; handled by trim_repetition
  token   — adjacent word loops ("parameter parameter parameter"); scattered
  subword — loops inside one word ("thresholdinginginging"); invisible to every
            word-level metric because it is a single unique word

Detection is the point. Serving stacks mask loops rather than fix them, so a
cleaner that silently tidies the overflow hides model damage. Order: report →
retry → repair.

Thresholds calibrated on English prose, ~100-250 words: 0 false positives on
~675 clean texts, 15/15 true positives on known-bad masked output.
"""

import re

from .repetition import trim_repetition
from ._log import log_failure

_DISTINCT_RATIO_MIN = 0.35     # below -> vocabulary collapse
_TOP_TOKEN_FRAC_MAX = 0.30     # above -> single-token fixation
_ADJACENT_DUP_MAX = 0.10       # above -> token loops
_INTRA_WORD_MAX = 0.05         # above -> subword loops

# Below this, one repeated token swings the rates; flags become weak evidence.
_SHORT_TEXT_WORDS = 30

_MIN_WORD_RUN = 3

# >=3 chars so natural doubles pass: "banana" (an-an) ok, "couscous" (cous) trips.
_INTRA_WORD_RE = re.compile(r"(\w{3,})\1")

_WORD_RUN_RE = re.compile(r"\b(\w+)(?:\s+\1\b){%d,}" % (_MIN_WORD_RUN - 1),
                          re.IGNORECASE)

# Sentence terminators across scripts, not just ASCII. A Latin-only set flagged
# 100% of Hindi (danda) and Chinese (ideographic stop) output as truncated.
_TERMINAL_PUNCT = (
    ".!?…\"')]}"          # latin
    "।॥"                   # devanagari danda, double danda
    "。！？．"              # cjk full stop, fullwidth ! ? .
    "」』）】〉》"          # cjk closing quotes and brackets
    "۔؟"                   # urdu full stop, arabic question mark
    "។"                    # khmer
    "።፧"                   # ethiopic
)

# A closing code fence is a structural end, not a mid-thought cut.
_FENCE_END = "```"

_SCRIPT_RANGES = (
    ("latin", ((0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x024F))),
    ("greek", ((0x0370, 0x03FF), (0x1F00, 0x1FFF))),
    ("cyrillic", ((0x0400, 0x052F),)),
)
_DEFAULT_CONFUSABLE_SCRIPTS = ("latin", "cyrillic", "greek")

_EMPTY_REPORT = {
    "degenerate": False, "rules_fired": [], "short_text": True, "word_count": 0,
    "distinct_ratio": 1.0, "top_token_frac": 0.0, "adjacent_dup_rate": 0.0,
    "intra_word_rate": 0.0, "phrase_repetition": False, "truncated": False,
    "mixed_script_words": [],
}


def adjacent_dup_rate(text: str) -> float:
    """Fraction of adjacent word pairs that are identical. Token-loop signal."""
    if not isinstance(text, str):
        return 0.0
    words = [w.lower() for w in text.split()]
    if len(words) < 2:
        return 0.0
    return sum(1 for i in range(1, len(words)) if words[i] == words[i - 1]) / (len(words) - 1)


def intra_word_rate(text: str) -> float:
    """Fraction of words with an adjacent repeated substring. Subword-loop signal.

    False-positives on genuine reduplication ("couscous"). Hyphenated forms
    ("orang-orang") do not trip it — \\w does not cross the hyphen.
    """
    if not isinstance(text, str):
        return 0.0
    words = text.split()
    if not words:
        return 0.0
    return sum(1 for w in words if _INTRA_WORD_RE.search(w)) / len(words)


def looks_truncated(text: str, cap_tokens: int = None) -> bool:
    """Output cut mid-thought. Separate axis from repetition: different cause, different fix.

    Prefer the provider's finish_reason when you have it; this is the fallback.
    """
    if not isinstance(text, str):
        return False
    stripped = text.rstrip()
    if not stripped:
        return False
    if stripped.endswith(_FENCE_END):
        return False
    unterminated = stripped[-1] not in _TERMINAL_PUNCT
    if cap_tokens:
        return unterminated and len(stripped.split()) >= 0.9 * cap_tokens
    return unterminated


def _script_of(ch: str):
    cp = ord(ch)
    for name, ranges in _SCRIPT_RANGES:
        for lo, hi in ranges:
            if lo <= cp <= hi:
                return name
    return None


def mixed_script_words(text: str, scripts=_DEFAULT_CONFUSABLE_SCRIPTS) -> list:
    """Words mixing >1 script internally (e.g. "ReLУ" with a Cyrillic У).

    Only word-internal mixing is a signal — document-level mixing is normal in
    Hinglish and any bilingual text.
    """
    if not isinstance(text, str):
        return []
    wanted = set(scripts)
    hits = []
    for word in text.split():
        if len({s for s in (_script_of(c) for c in word) if s in wanted}) > 1:
            hits.append(word)
    return hits


def degeneracy_score(text: str, cap_tokens: int = None,
                     scripts=_DEFAULT_CONFUSABLE_SCRIPTS) -> dict:
    """Report degeneration signals without modifying the text.

    `degenerate` is the OR of five rules. They overlap but none is redundant:
    the subword sample passes all four word-level rules, total collapse passes
    the subword rule, and phrase loops pass all four because their words
    alternate. `truncated` and `mixed_script_words` are reported but excluded
    from the verdict — separate axes, separate fixes.
    """
    if not isinstance(text, str):
        return dict(_EMPTY_REPORT)
    try:
        words = [w.lower() for w in text.split()]
        n = len(words)
        denom = max(n, 1)

        counts = {}
        for w in words:
            counts[w] = counts.get(w, 0) + 1

        distinct = len(set(words)) / denom if n else 1.0
        top_frac = (max(counts.values()) / denom) if counts else 0.0
        adj = adjacent_dup_rate(text)
        intra = intra_word_rate(text)
        phrase = trim_repetition(text) != text   # phrase loops need the n-gram machinery

        fired = []
        if n and distinct < _DISTINCT_RATIO_MIN:
            fired.append("distinct_ratio")
        if top_frac > _TOP_TOKEN_FRAC_MAX:
            fired.append("top_token_frac")
        if adj > _ADJACENT_DUP_MAX:
            fired.append("adjacent_dup_rate")
        if intra > _INTRA_WORD_MAX:
            fired.append("intra_word_rate")
        if phrase:
            fired.append("phrase_repetition")

        return {
            "degenerate": bool(fired),
            "rules_fired": fired,
            "short_text": n < _SHORT_TEXT_WORDS,
            "word_count": n,
            "distinct_ratio": distinct,
            "top_token_frac": top_frac,
            "adjacent_dup_rate": adj,
            "intra_word_rate": intra,
            "phrase_repetition": phrase,
            "truncated": looks_truncated(text, cap_tokens),
            "mixed_script_words": mixed_script_words(text, scripts),
        }
    except Exception as _e:
        log_failure("degeneracy_score", _e)
        return dict(_EMPTY_REPORT)


def collapse_word_runs(text: str) -> str:
    """Collapse runs of 3+ identical adjacent words to one.

    Runs of 2 are left alone — "had had", "that that" are real English.

    Run length depends on which anti-repetition mechanism your stack uses, so
    do not tune for a specific length:
      hard trigram ban (HF no_repeat_ngram_size=3) truncates an unbounded
        X X X X... loop at the fourth X -> exactly-3 runs, never longer
      soft logit penalty (llama.cpp/Ollama repeat_penalty) -> either no runs
        (penalty on) or unbounded runs (measured: 61 identical words, gemma4
        with repeat_penalty=1.0)
    Collapsing at >=3 covers both.
    """
    if not isinstance(text, str):
        return text
    try:
        return _WORD_RUN_RE.sub(r"\1", text)
    except Exception as _e:
        log_failure("collapse_word_runs", _e)
        return text


def collapse_intra_word_runs(text: str, max_passes: int = 10) -> str:
    """Collapse repeated substrings inside words. Opt-in, best effort, lossy.

    Iterates to a fixpoint since one pass leaves residue
    ("backproppropagationagationation"). Also collapses genuine reduplication
    ("couscous" -> "cous"). A tripped intra_word_rate usually means the
    generation should be retried, not repaired.
    """
    if not isinstance(text, str):
        return text
    try:
        for _ in range(max_passes):
            new = _INTRA_WORD_RE.sub(r"\1", text)
            if new == text:
                break
            text = new
        return text
    except Exception as _e:
        log_failure("collapse_intra_word_runs", _e)
        return text
