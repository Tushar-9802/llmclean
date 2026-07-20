"""
api.py — the three front doors.

Nearly every caller arrives with one of three goals:

    data   = llmclean.load_json(raw)    # I asked for JSON, give me a dict
    text   = llmclean.clean_text(raw)   # I asked for prose, give me clean prose
    report = llmclean.check(raw)        # is this output broken?

Each composes the lower-level functions with sane defaults. Reach past them for
per-step control.
"""

import json as _json

from ._log import log_failure, log_fallback
from .degeneracy import degeneracy_score
from .json_utils import enforce_json
from .markdown import strip_markdown
from .prose import strip_preamble, strip_reasoning_trace
from .repetition import trim_repetition
from .unicode_norm import normalize_typography, strip_invisibles


def load_json(text, default=None):
    """Parse JSON out of messy model output. Returns a dict/list, or *default*.

    Strips reasoning traces first so a <think> block containing braces cannot
    confuse extraction, then runs the enforce_json repair pipeline. Never raises.
    """
    if not isinstance(text, str):
        return default
    try:
        return _json.loads(enforce_json(strip_reasoning_trace(text)))
    except Exception as e:
        # Expected outcome when there is simply no JSON in the text.
        log_fallback("load_json", "no parseable JSON (%s)" % type(e).__name__)
        return default


def clean_text(text, *, reasoning=True, preamble=True, markdown=True,
               typography=True, repetition=False):
    """Turn raw model output into plain prose.

    Order: reasoning trace -> conversational filler -> markdown -> invisible
    characters -> typography. Invisible-character stripping always runs; it is
    never destructive.

    ``repetition`` is off by default: trimming it silently would hide model
    damage, which is what ``check`` exists to surface. Turn it on only when you
    cannot regenerate.
    """
    if not isinstance(text, str):
        return text
    try:
        if reasoning:
            text = strip_reasoning_trace(text)
        if preamble:
            text = strip_preamble(text)
        if markdown:
            text = strip_markdown(text)
        text = strip_invisibles(text)
        if typography:
            text = normalize_typography(text)
        if repetition:
            text = trim_repetition(text)
        return text.strip()
    except Exception as e:
        log_failure("clean_text", e)
        return text


def check(text, cap_tokens=None):
    """Report degeneration signals without modifying the text. See degeneracy_score."""
    return degeneracy_score(text, cap_tokens=cap_tokens)
