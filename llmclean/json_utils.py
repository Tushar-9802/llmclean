"""
json_utils.py — extract and repair valid JSON from messy LLM output.

LLMs routinely return JSON wrapped in prose, fences, or with small syntax
errors.  This module tries a pipeline of increasingly aggressive strategies
to get back a valid, parse-able JSON string.

Strategy pipeline (stops at first success):
  1. Parse as-is (already valid JSON)
  2. Strip fences then parse
  3. Strip leading/trailing prose, leaving only the JSON substring
     (handles "Sure! Here is your JSON: {...} Hope that helps!")
  4. Remove trailing commas before ] or }
  5. Attempt to fix unquoted keys  (moderate repair)
  6. Attempt to close unclosed brackets/braces
  7. Combination of fixes 4+5+6

If every strategy fails the original text is returned unchanged so the
caller can decide what to do.
"""

import json
import re
from .fences import strip_fences
from ._log import log_failure


# Byte Order Mark — U+FEFF. Some LLM client SDKs and any pipeline that
# round-trips through Windows file IO prepend a BOM. json.loads sees it as
# "Unexpected character at position 0" and bails. We strip it up-front.
_BOM = "﻿"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enforce_json(text: str) -> str:
    """Attempt to extract and return valid JSON from *text*.

    Applies a pipeline of cleaning strategies.  The first strategy that
    produces parse-able JSON wins; its output (the cleaned JSON string) is
    returned.  If nothing works the original text is returned unchanged.

    The returned string, when a strategy succeeds, is re-serialized with
    ``json.dumps`` so it is always consistently formatted.

    Parameters
    ----------
    text:
        Raw LLM output that should contain JSON somewhere.

    Returns
    -------
    str
        A valid JSON string, or the original *text* if extraction failed.
    """
    if not isinstance(text, str):
        return text

    original = text

    try:
        return _run_pipeline(text.lstrip(_BOM).strip())
    except Exception as _e:
        log_failure("enforce_json", _e)
        return original


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _run_pipeline(text: str) -> str:
    strategies = [
        _try_parse_direct,
        _try_strip_fences,
        _try_extract_json_substring,
        _try_collapse_double_quotes,
        _try_fix_trailing_commas,
        _try_fix_python_literals,
        _try_fix_unquoted_keys,
        _try_close_open_brackets,
        _try_combined_fixes,
    ]
    for strategy in strategies:
        result = strategy(text)
        if result is not None:
            return result
    # Nothing worked — return original
    return text


# ---------------------------------------------------------------------------
# Strategies (each returns a clean JSON *string* or None)
# ---------------------------------------------------------------------------

def _try_parse_direct(text: str):
    """Strategy 1: already valid JSON."""
    return _parse_and_serialize(text)


def _try_strip_fences(text: str):
    """Strategy 2: strip code fences then parse."""
    stripped = strip_fences(text)
    if stripped == text:
        return None  # no change, skip
    return _parse_and_serialize(stripped)


def _try_extract_json_substring(text: str):
    """Strategy 3: find the first JSON object or array in the text.

    Scans for the first '{' or '[' and tries progressively larger substrings
    until one parses.  Also tries from the *last* '}' or ']' backwards.
    This handles patterns like:
        'Sure, here is the data: {"key": "value"} Let me know if...'
    """
    # Try object extraction
    result = _extract_by_brackets(text, "{", "}")
    if result is not None:
        return result
    # Try array extraction
    return _extract_by_brackets(text, "[", "]")


def _extract_by_brackets(text: str, open_char: str, close_char: str):
    """Find the outermost balanced bracket pair and try to parse it."""
    start = text.find(open_char)
    if start == -1:
        return None

    end = text.rfind(close_char)
    if end == -1 or end <= start:
        return None

    # Try from outermost to innermost close bracket
    candidate = text[start:end + 1]
    result = _parse_and_serialize(candidate)
    if result is not None:
        return result

    # Walk inward if the outer attempt fails (handles trailing junk)
    for i in range(end - 1, start, -1):
        if text[i] == close_char:
            result = _parse_and_serialize(text[start:i + 1])
            if result is not None:
                return result
    return None


def _try_collapse_double_quotes(text: str):
    '''Strategy: collapse doubled-quote wrappers around content to single quotes.

    Models occasionally emit doubled-quote overruns like ``{"key": ""value""}``
    or higher-order forms from Python f-string / triple-string leaks. We ONLY
    collapse the form ""<content>"" where there is non-empty content between
    the doubled quotes. Sakhi's `_parse_json_response` also collapses the
    asymmetric forms ``: ""x`` and ``x"",`` but those patterns can corrupt
    legitimate empty-string values (``{"k": ""}``, ``["", "x"]``) because
    there is no way to tell from the regex alone whether the "" is overrun
    or empty. The content-required form here is unambiguous and safe.'''
    cleaned = _collapse_double_quote_wrappers(text)
    if cleaned == text:
        return None
    return _parse_and_serialize(cleaned)


def _try_fix_trailing_commas(text: str):
    """Strategy 4: remove trailing commas before closing brackets."""
    cleaned = _remove_trailing_commas(text)
    if cleaned == text:
        return None
    return _parse_and_serialize(cleaned)


def _try_fix_python_literals(text: str):
    """Strategy 5: replace Python literals that LLMs emit instead of JSON.

    LLMs frequently output Python-style values inside otherwise valid JSON:
        True / False / None  ->  true / false / null
        Single-quoted strings: {'key': 'val'}  ->  {"key": "val"}

    Applied word-boundary-aware so legitimate content is not corrupted.
    """
    cleaned = _replace_python_literals(text)
    if cleaned == text:
        return None
    return _parse_and_serialize(cleaned)


def _try_fix_unquoted_keys(text: str):
    """Strategy 6: quote bare word keys like {key: value} -> {"key": value}."""
    cleaned = _quote_unquoted_keys(text)
    if cleaned == text:
        return None
    return _parse_and_serialize(cleaned)


def _try_close_open_brackets(text: str):
    """Strategy 7: append missing closing brackets/braces."""
    cleaned = _close_open_structures(text)
    if cleaned == text:
        return None
    return _parse_and_serialize(cleaned)


def _try_combined_fixes(text: str):
    """Strategy 8: apply all fixers in sequence."""
    cleaned = _replace_python_literals(text)
    cleaned = _remove_trailing_commas(cleaned)
    cleaned = _quote_unquoted_keys(cleaned)
    cleaned = _close_open_structures(cleaned)
    if cleaned == text:
        return None
    # Also try substring extraction on the combined fix
    result = _parse_and_serialize(cleaned)
    if result is not None:
        return result
    return _try_extract_json_substring(cleaned)


# ---------------------------------------------------------------------------
# Fixers
# ---------------------------------------------------------------------------

# Trailing comma before } or ]  (also handles whitespace/newlines between)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")

def _remove_trailing_commas(text: str) -> str:
    return _TRAILING_COMMA_RE.sub(r"\1", text)


# Double-quote-wrapper collapse: ""text"" → "text"
# Requires non-empty content between the doubled quotes so legitimate empty
# strings ("") are never matched. See _try_collapse_double_quotes docstring
# for why we don't include the asymmetric Sakhi patterns.
_DOUBLE_QUOTE_WRAPPER_RE = re.compile(r'"{2,}([^"]+)"{2,}')

def _collapse_double_quote_wrappers(text: str) -> str:
    return _DOUBLE_QUOTE_WRAPPER_RE.sub(r'"\1"', text)


# Bare (unquoted) object keys:  { key: ... }  →  { "key": ... }
# Only matches word-characters; won't disturb already-quoted keys.
_UNQUOTED_KEY_RE = re.compile(r'(?<!["\w])(\b[a-zA-Z_][a-zA-Z0-9_]*\b)\s*(?=:)')

def _quote_unquoted_keys(text: str) -> str:
    # Only operate inside what looks like a JSON object
    start = text.find("{")
    if start == -1:
        return text
    prefix = text[:start]
    body = text[start:]
    fixed = _UNQUOTED_KEY_RE.sub(r'"\1"', body)
    return prefix + fixed


def _close_open_structures(text: str) -> str:
    """Append any missing closing } or ] characters."""
    stack = []
    in_string = False
    escape_next = False
    pairs = {"{": "}", "[": "]"}
    closers = set(pairs.values())

    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in pairs:
            stack.append(pairs[ch])
        elif ch in closers:
            if stack and stack[-1] == ch:
                stack.pop()

    # Append missing closers in reverse order
    return text + "".join(reversed(stack))


# ---------------------------------------------------------------------------
# Helpers used by the fixers above
# ---------------------------------------------------------------------------

def _parse_and_serialize(text: str):
    """Try to parse *text* as JSON; return re-serialized string or None."""
    try:
        parsed = json.loads(text.strip())
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Python-literal fixer (state-aware, single pass)
# ---------------------------------------------------------------------------

# Python boolean/None literals and their JSON equivalents.
_PYTHON_LITERAL_MAP = {"True": "true", "False": "false", "None": "null"}


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _replace_python_literals(text: str) -> str:
    """Replace Python ``True``/``False``/``None`` with JSON ``true``/``false``/``null``
    and convert single-quoted strings to double-quoted — both in one
    string-state-aware pass.

    The earlier implementation did a blind ``re.sub`` for the literals, which
    silently corrupted the same words when they appeared *inside* a string
    value (``{"note": "set flag to True"}`` → ``...to true``). A regex cannot
    tell a bare ``True`` token from the substring ``True`` inside quoted
    content, so the only correct fix is to track string state and only rewrite
    literals that sit *outside* any string.

    Rules while scanning:
      * Inside a double-quoted string: copy verbatim (respecting ``\\`` escapes)
        until the closing quote — literals here are content, never touched.
      * Inside a single-quoted string: rewrite the delimiters to ``"``, escape
        any bare ``"`` that appears in the content, and copy the rest verbatim.
      * Outside any string: rewrite a ``'`` to ``"`` (string start) and replace
        a word-boundary-delimited ``True``/``False``/``None`` token.
    """
    out = []
    i = 0
    n = len(text)
    in_double = False
    in_single = False

    while i < n:
        ch = text[i]

        if in_double:
            # Copy verbatim; honour backslash escapes so an escaped quote
            # does not prematurely end the string.
            if ch == "\\" and i + 1 < n:
                out.append(ch)
                out.append(text[i + 1])
                i += 2
                continue
            out.append(ch)
            if ch == '"':
                in_double = False
            i += 1
            continue

        if in_single:
            if ch == "\\" and i + 1 < n:
                out.append(ch)
                out.append(text[i + 1])
                i += 2
                continue
            if ch == "'":
                out.append('"')          # closing single quote -> double
                in_single = False
                i += 1
                continue
            if ch == '"':
                out.append('\\"')        # bare double inside content -> escape
                i += 1
                continue
            out.append(ch)
            i += 1
            continue

        # --- outside any string ---
        if ch == '"':
            in_double = True
            out.append(ch)
            i += 1
            continue
        if ch == "'":
            in_single = True
            out.append('"')              # opening single quote -> double
            i += 1
            continue

        # Try to match a Python literal token at this position.
        for word, repl in _PYTHON_LITERAL_MAP.items():
            if not text.startswith(word, i):
                continue
            before_ok = i == 0 or not _is_word_char(text[i - 1])
            end = i + len(word)
            after_ok = end >= n or not _is_word_char(text[end])
            if before_ok and after_ok:
                out.append(repl)
                i = end
                break
        else:
            out.append(ch)
            i += 1

    return "".join(out)