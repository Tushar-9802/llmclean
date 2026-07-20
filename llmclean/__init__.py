"""
llmclean — utilities for cleaning and normalizing raw LLM output.

Quick start — three front doors::

    import llmclean

    data   = llmclean.load_json(raw)    # messy output -> dict/list (or None)
    text   = llmclean.clean_text(raw)   # messy output -> plain prose
    report = llmclean.check(raw)        # is this output degenerate?

Reach past them when you need per-step control::

    from llmclean import strip_fences, enforce_json, trim_repetition
    from llmclean import strip_reasoning_trace, strip_preamble
    from llmclean import strip_invisibles, normalize_typography, strip_markdown
    from llmclean import degeneracy_score, collapse_word_runs
"""

from ._log import enable_debug_logging, logger
from .api import load_json, clean_text, check
from .fences import strip_fences
from .json_utils import enforce_json
from .repetition import trim_repetition
from .prose import strip_reasoning_trace, strip_preamble
from .unicode_norm import strip_invisibles, normalize_typography
from .markdown import strip_markdown
from .degeneracy import (
    degeneracy_score,
    adjacent_dup_rate,
    intra_word_rate,
    looks_truncated,
    mixed_script_words,
    collapse_word_runs,
    collapse_intra_word_runs,
)

__all__ = [
    # front doors — start here
    "load_json",
    "clean_text",
    "check",
    # lower-level, for per-step control
    "strip_fences",
    "enforce_json",
    "trim_repetition",
    "strip_reasoning_trace",
    "strip_preamble",
    "strip_invisibles",
    "normalize_typography",
    "strip_markdown",
    # degeneration: detect first, repair only if you cannot regenerate
    "degeneracy_score",
    "adjacent_dup_rate",
    "intra_word_rate",
    "looks_truncated",
    "mixed_script_words",
    "collapse_word_runs",
    "collapse_intra_word_runs",
    # debugging
    "enable_debug_logging",
    "logger",
]
__version__ = "0.4.0"