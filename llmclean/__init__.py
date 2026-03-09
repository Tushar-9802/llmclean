"""
llmclean — utilities for cleaning and normalizing raw LLM output.

Quick start::

    from llmclean import strip_fences, enforce_json, trim_repetition

    clean = strip_fences(raw_output)
    data  = enforce_json(raw_output)
    text  = trim_repetition(raw_output)
"""

from .fences import strip_fences
from .json_utils import enforce_json
from .repetition import trim_repetition

__all__ = ["strip_fences", "enforce_json", "trim_repetition"]
__version__ = "0.1.0"