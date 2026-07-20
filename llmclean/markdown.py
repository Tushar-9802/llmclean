"""
markdown.py — flatten markdown-formatted LLM output to plain prose.

Models emit markdown (**bold**, ## headers, - bullets, [links](url), inline
`code`, tables) even when asked for plain text. That breaks text-to-speech
("reads 'hashtag hashtag Introduction'"), voice/chat bots, SMS, plain UI
fields, and any consumer that wants prose, not formatting.

``strip_markdown`` removes the formatting markup and keeps the readable text.
It is intentionally a best-effort flattener aimed at the TTS / plain-text use
case, not a markdown parser — when in doubt it preserves the text content and
drops only the markup characters.

Empirical note: markdown formatting was the single most common output trait in
a 5-model local baseline (llama/gemma/qwen/deepseek/mistral) — it appeared on
every "explain with headers/bullets", code, and table prompt — so this is the
highest-frequency non-fence cleanup need.
"""

import re

from .fences import strip_fences
from ._log import log_failure

# Code fences are handled by strip_fences (keeps inner code). Everything below
# operates line- or span-wise on the de-fenced text.

# Images first (so the ![alt](url) form is consumed before the link rule):
#   ![alt](url) -> alt
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
# Links:  [text](url) -> text  ;  [text][ref] -> text
_LINK_INLINE_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_LINK_REF_RE = re.compile(r"\[([^\]]+)\]\[[^\]]*\]")

# ATX headers:  ###  Title  ->  Title   (also strips a trailing ' ###')
_HEADER_RE = re.compile(r"^[ \t]*#{1,6}[ \t]+(.*?)[ \t]*#*[ \t]*$", re.MULTILINE)

# Blockquote markers at line start:  > quoted  ->  quoted
_BLOCKQUOTE_RE = re.compile(r"^[ \t]*>[ \t]?", re.MULTILINE)

# Unordered list markers:  -  *  +   at line start (require following space so a
# bare '*' inside prose or a '-' in a number range is left alone).
_BULLET_RE = re.compile(r"^([ \t]*)[-*+][ \t]+", re.MULTILINE)

# Ordered list markers:  1.  2)   at line start.
_ORDERED_RE = re.compile(r"^([ \t]*)\d+[.)][ \t]+", re.MULTILINE)

# Horizontal rules:  ---   ***   ___   (3+ on their own line).
_HR_RE = re.compile(r"^[ \t]*([-*_])(?:[ \t]*\1){2,}[ \t]*$", re.MULTILINE)

# Emphasis spans. Order matters: bold (**/__) before italic (*/_), and we run a
# couple of passes so ***bold italic*** unwinds. Underscore emphasis requires
# word boundaries so snake_case identifiers survive.
_BOLD_AST_RE = re.compile(r"\*\*([^\n]+?)\*\*")
_BOLD_UND_RE = re.compile(r"(?<![\w_])__([^\n]+?)__(?![\w_])")
_ITALIC_AST_RE = re.compile(r"\*([^\s*][^\n]*?)\*")
_ITALIC_UND_RE = re.compile(r"(?<![\w_])_([^\s_][^\n]*?)_(?![\w_])")
_STRIKE_RE = re.compile(r"~~([^\n]+?)~~")

# Inline code:  `code` -> code
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")

# Table pipe/sep cleanup: a separator row of |---|:--:| etc becomes empty; data
# rows keep cell text with single spaces instead of pipes.
_TABLE_SEP_RE = re.compile(r"^[ \t]*\|?[ \t]*:?-{2,}:?[ \t]*(\|[ \t]*:?-{2,}:?[ \t]*)*\|?[ \t]*$",
                           re.MULTILINE)

_MULTI_BLANK_RE = re.compile(r"\n{3,}")


def _strip_emphasis(text: str) -> str:
    for _ in range(3):  # unwind nested emphasis (***x***, **_x_**)
        new = _BOLD_AST_RE.sub(r"\1", text)
        new = _BOLD_UND_RE.sub(r"\1", new)
        new = _ITALIC_AST_RE.sub(r"\1", new)
        new = _ITALIC_UND_RE.sub(r"\1", new)
        new = _STRIKE_RE.sub(r"\1", new)
        if new == text:
            break
        text = new
    return text


def _flatten_table_row(line: str) -> str:
    """Turn a '| a | b | c |' table row into 'a  b  c' (non-separator rows)."""
    stripped = line.strip()
    if not (stripped.startswith("|") or "|" in stripped):
        return line
    cells = [c.strip() for c in stripped.strip("|").split("|")]
    return "  ".join(c for c in cells if c)


def strip_markdown(text: str) -> str:
    """Remove markdown formatting from *text*, keeping the readable text.

    Handles code fences (via ``strip_fences``), ATX headers, bold/italic/
    strikethrough emphasis, inline code, links and images, block quotes,
    unordered/ordered list markers, horizontal rules, and basic pipe tables.

    Best-effort and conservative: identifiers like ``snake_case`` and ``a-b``
    ranges are preserved because the list/emphasis rules require the markup to
    sit at a line start or span boundary. Returns cleaned prose; never raises.
    """
    if not isinstance(text, str):
        return text

    original = text
    try:
        # 1. Unwrap code fences (keeps inner content).
        text = strip_fences(text)

        # 2. Remove horizontal rules and table separator rows entirely.
        text = _HR_RE.sub("", text)
        text = _TABLE_SEP_RE.sub("", text)

        # 3. Headers, blockquotes, list markers (line-anchored).
        text = _HEADER_RE.sub(r"\1", text)
        text = _BLOCKQUOTE_RE.sub("", text)
        text = _BULLET_RE.sub(r"\1", text)
        text = _ORDERED_RE.sub(r"\1", text)

        # 4. Images, then links, then emphasis, then inline code (span-level).
        text = _IMAGE_RE.sub(r"\1", text)
        text = _LINK_INLINE_RE.sub(r"\1", text)
        text = _LINK_REF_RE.sub(r"\1", text)
        text = _strip_emphasis(text)
        text = _INLINE_CODE_RE.sub(r"\1", text)

        # 5. Flatten remaining table rows.
        if "|" in text:
            text = "\n".join(_flatten_table_row(ln) for ln in text.split("\n"))

        # 6. Tidy whitespace introduced by removals.
        text = _MULTI_BLANK_RE.sub("\n\n", text)
        text = "\n".join(ln.rstrip() for ln in text.split("\n"))
        return text.strip()
    except Exception as _e:
        log_failure("strip_markdown", _e)
        return original
