"""
llmclean — utilities for cleaning and normalizing raw LLM output.

Quick start::

    from llmclean import strip_fences, enforce_json, trim_repetition
    from llmclean import strip_reasoning_trace, strip_preamble
    from llmclean import strip_invisibles, normalize_typography, strip_markdown

    clean = strip_fences(raw_output)
    data  = enforce_json(raw_output)
    text  = trim_repetition(raw_output)
    text  = strip_reasoning_trace(raw_output)   # drop <think>...</think>
    text  = strip_preamble(raw_output)          # drop "Sure! Here's ..."
    text  = strip_invisibles(raw_output)        # drop zero-width / control chars
    text  = normalize_typography(raw_output)    # smart quotes/dashes/… -> ASCII
    text  = strip_markdown(raw_output)          # flatten markdown to prose
"""

from .fences import strip_fences
from .json_utils import enforce_json
from .repetition import trim_repetition
from .prose import strip_reasoning_trace, strip_preamble
from .unicode_norm import strip_invisibles, normalize_typography
from .markdown import strip_markdown

__all__ = [
    "strip_fences",
    "enforce_json",
    "trim_repetition",
    "strip_reasoning_trace",
    "strip_preamble",
    "strip_invisibles",
    "normalize_typography",
    "strip_markdown",
]
__version__ = "0.3.0"