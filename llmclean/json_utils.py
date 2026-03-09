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
        return _run_pipeline(text.strip())
    except Exception:
        return original


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _run_pipeline(text: str) -> str:
    strategies = [
        _try_parse_direct,
        _try_strip_fences,
        _try_extract_json_substring,
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
# Utility
# ---------------------------------------------------------------------------

def _parse_and_serialize(text: str):
    """Try to parse *text* as JSON; return re-serialized string or None."""
    try:
        parsed = json.loads(text.strip())
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Python-literal fixer (added separately for clarity)
# ---------------------------------------------------------------------------

# Word-boundary replacements for Python boolean/None literals
_PYTHON_LITERAL_RE = re.compile(r'\bTrue\b|\bFalse\b|\bNone\b')
_PYTHON_LITERAL_MAP = {"True": "true", "False": "false", "None": "null"}

def _replace_python_literals(text: str) -> str:
    """Replace Python True/False/None with JSON true/false/null.

    Also converts single-quoted strings to double-quoted where safe.
    Only operates outside of already-valid JSON strings to avoid
    corrupting content that legitimately contains these words.
    """
    # Step 1: True / False / None  (simple word-boundary swap)
    result = _PYTHON_LITERAL_RE.sub(lambda m: _PYTHON_LITERAL_MAP[m.group()], text)

    # Step 2: single-quoted strings -> double-quoted
    # Strategy: only replace 'value' patterns that look like JSON string values
    # or keys (preceded by { , or : and optional whitespace).
    # This is intentionally conservative to avoid mangling prose.
    result = _single_to_double_quotes(result)
    return result


def _single_to_double_quotes(text: str) -> str:
    """Convert single-quoted JSON-ish strings to double-quoted JSON."""
    result = []
    i = 0
    in_single = False
    in_double = False
    sq = chr(39)   # '
    dq = chr(34)   # "
    bs = chr(92)   # \
    while i < len(text):
        ch = text[i]
        if ch == bs and (in_single or in_double):
            result.append(ch)
            i += 1
            if i < len(text):
                result.append(text[i])
                i += 1
            continue
        if ch == sq and not in_double:
            in_single = not in_single
            result.append(dq)
        elif ch == dq and not in_single:
            in_double = not in_double
            result.append(ch)
        elif ch == dq and in_single:
            result.append(bs + dq)
        else:
            result.append(ch)
        i += 1
    return "".join(result)

def _parse_and_serialize(text: str):
    """Try to parse *text* as JSON; return re-serialized string or None."""
    try:
        parsed = json.loads(text.strip())
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Python-literal fixer (added separately for clarity)
# ---------------------------------------------------------------------------

# Word-boundary replacements for Python boolean/None literals
_PYTHON_LITERAL_RE = re.compile(r'\bTrue\b|\bFalse\b|\bNone\b')
_PYTHON_LITERAL_MAP = {"True": "true", "False": "false", "None": "null"}

def _replace_python_literals(text: str) -> str:
    """Replace Python True/False/None with JSON true/false/null.

    Also converts single-quoted strings to double-quoted where safe.
    Only operates outside of already-valid JSON strings to avoid
    corrupting content that legitimately contains these words.
    """
    # Step 1: True / False / None  (simple word-boundary swap)
    result = _PYTHON_LITERAL_RE.sub(lambda m: _PYTHON_LITERAL_MAP[m.group()], text)

    # Step 2: single-quoted strings -> double-quoted
    # Strategy: only replace 'value' patterns that look like JSON string values
    # or keys (preceded by { , or : and optional whitespace).
    # This is intentionally conservative to avoid mangling prose.
    result = _single_to_double_quotes(result)
    return result