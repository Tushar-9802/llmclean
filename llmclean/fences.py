"""
fences.py — strip markdown code fences from LLM output.

LLMs frequently wrap their output in fences like:
    ```json
    { "key": "value" }
    ```

This module handles:
  - Named fences:      ```json ... ```
  - Anonymous fences:  ``` ... ```
  - Tilde fences:      ~~~ ... ~~~
  - Indented fences:   leading whitespace before the backticks
  - Multiple fences in one string (strips all of them)
  - Nested / back-to-back fences
  - Fences with no closing marker (strips opening line, returns rest)
  - Stray language tags left on their own line after stripping
"""

import re

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Matches an opening fence line, e.g.  ```json  or  ```  or  ~~~python
# Group 1: the fence characters (``` or ~~~)
# Group 2: optional language identifier (may be empty)
_OPEN_FENCE_RE = re.compile(
    r"^[ \t]*(?P<fence>`{3,}|~{3,})[ \t]*(?P<lang>[a-zA-Z0-9_+\-.]*)[ \t]*$",
    re.MULTILINE,
)

# Matches a closing fence: same or more fence characters on its own line
_CLOSE_FENCE_RE = re.compile(
    r"^[ \t]*(?P<fence>`{3,}|~{3,})[ \t]*$",
    re.MULTILINE,
)

# After all fences are stripped, clean up lone language-tag lines that were
# sitting right above the content, e.g. a line that is just "json" or "python"
# This is intentionally narrow to avoid removing real content.
_LONE_LANG_TAG_RE = re.compile(
    r"^[ \t]*(?:json|python|javascript|js|typescript|ts|bash|sh|shell|"
    r"html|xml|css|yaml|yml|toml|ini|markdown|md|text|txt|plaintext|"
    r"sql|graphql|rust|go|java|c|cpp|c\+\+|csharp|cs|ruby|rb|php|"
    r"swift|kotlin|scala|r|lua|perl|haskell|elixir|erlang|clojure|"
    r"dart|objc|output|console|log)[ \t]*$",
    re.MULTILINE | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def strip_fences(text: str) -> str:
    """Remove all markdown/tilde code fences from *text*.

    Strips every fenced block found, replacing each fence with the raw
    content that was inside it.  If no fences are present the original
    text is returned unchanged.  The function never raises.

    Parameters
    ----------
    text:
        Raw LLM output that may contain one or more fenced code blocks.

    Returns
    -------
    str
        The cleaned text with fence markers removed and inner content
        preserved.  Leading/trailing whitespace that was *outside* all
        fences is also stripped.
    """
    if not isinstance(text, str):
        return text  # defensive: wrong type → return as-is

    original = text

    try:
        result = _strip_all_fences(text)
        # Collapse any excessive blank lines introduced by fence removal
        result = _normalize_blank_lines(result)
        return result
    except Exception:
        # Safety net: never crash the caller
        return original


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _strip_all_fences(text: str) -> str:
    """Iteratively strip fences until no more remain."""
    # We loop because fences can be back-to-back; each pass removes one layer.
    for _ in range(50):  # guard against pathological inputs
        new_text = _strip_one_pass(text)
        if new_text == text:
            break
        text = new_text

    # Clean up orphaned language-tag lines (e.g. a bare "json" line)
    text = _LONE_LANG_TAG_RE.sub("", text)
    return text.strip()


def _strip_one_pass(text: str) -> str:
    """Remove every complete (or unclosed) fence block found in *text*."""
    result_parts: list[str] = []
    cursor = 0

    for open_match in _OPEN_FENCE_RE.finditer(text):
        open_start = open_match.start()
        open_end = open_match.end()
        fence_chars = open_match.group("fence")
        fence_type = fence_chars[0]  # ` or ~

        # Append everything before this opening fence
        result_parts.append(text[cursor:open_start])

        # Look for a matching closing fence (same fence character, >= same length)
        close_match = _find_closing_fence(text, open_end, fence_type, len(fence_chars))

        if close_match:
            # Content between open and close fences
            inner = text[open_end:close_match.start()]
            result_parts.append(inner)
            cursor = close_match.end()
        else:
            # Unclosed fence: drop the opening line, keep the rest of the text
            inner = text[open_end:]
            result_parts.append(inner)
            cursor = len(text)
            break  # nothing left to process

    # Append any trailing text after the last fence
    result_parts.append(text[cursor:])

    return "".join(result_parts)


def _find_closing_fence(text: str, search_from: int, fence_type: str, min_len: int):
    """Return the first closing fence match at or after *search_from*."""
    for m in _CLOSE_FENCE_RE.finditer(text, search_from):
        fc = m.group("fence")
        if fc[0] == fence_type and len(fc) >= min_len:
            return m
    return None


def _normalize_blank_lines(text: str) -> str:
    """Collapse 3+ consecutive blank lines down to 2."""
    return re.sub(r"\n{3,}", "\n\n", text)