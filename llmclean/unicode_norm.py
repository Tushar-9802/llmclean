"""
unicode_norm.py — character-level normalization of LLM output.

Two functions:

  * ``strip_invisibles`` — remove zero-width and control characters that are
    invisible yet break search, regex, tokenization, equality checks, and
    copy-paste. Safe by default; the only nuance is preserving legitimate
    zero-width joiners inside emoji sequences (👨‍👩‍👧).

  * ``normalize_typography`` — map "published-prose" Unicode punctuation
    (smart quotes, em/en dashes, ellipsis character, non-breaking and exotic
    spaces, ligatures, and — opt-in — fullwidth forms) to plain ASCII.

Empirical note: across a 5-model local baseline (llama/gemma/qwen/deepseek/
mistral, 7-8B instruct), local models emit ASCII punctuation almost exclusively
— no smart quotes, ellipsis chars, NBSP, or ligatures appeared even when
prompted for them. The typography mess these functions target is overwhelmingly
a *frontier cloud-model* (ChatGPT/Claude/Gemini) trait that reaches a pipeline
when such output is pasted or piped in. Fullwidth punctuation does show up — but
only inside CJK *prose*, never in JSON structure — which is why fullwidth
normalization is its own opt-in category rather than on by default.
"""

import re

# ---------------------------------------------------------------------------
# strip_invisibles
# ---------------------------------------------------------------------------

# Code points removed unconditionally. C0/C1 controls EXCEPT tab/newline/CR are
# handled separately below so we never touch ordinary whitespace.
_INVISIBLE_CODEPOINTS = [
    0x00AD,            # soft hyphen
    0x180E,            # mongolian vowel separator
    0x200B,            # zero width space
    0x200C,            # zero width non-joiner
    # 0x200D zero width joiner is handled specially (emoji sequences)
    0x200E, 0x200F,    # LTR / RTL marks
    0x2028, 0x2029,    # line / paragraph separators
    0x202A, 0x202B, 0x202C, 0x202D, 0x202E,   # bidi embeddings/overrides
    0x2060,            # word joiner
    0x2061, 0x2062, 0x2063, 0x2064,           # invisible math operators
    0x2066, 0x2067, 0x2068, 0x2069,           # bidi isolates
    0xFEFF,            # BOM / zero width no-break space
    0xFFF9, 0xFFFA, 0xFFFB,                    # interlinear annotation
]

# Control characters to strip: C0 (0x00-0x1F) and DEL/C1 (0x7F-0x9F), keeping
# the three whitespace controls everyone actually wants.
_CONTROL_KEEP = {0x09, 0x0A, 0x0D}  # tab, newline, carriage return
_CONTROL_CODEPOINTS = [
    c for c in list(range(0x00, 0x20)) + list(range(0x7F, 0xA0))
    if c not in _CONTROL_KEEP
]

_INVISIBLE_TRANSLATE = {cp: None for cp in _INVISIBLE_CODEPOINTS + _CONTROL_CODEPOINTS}

# Zero-width joiner sitting between two non-ASCII chars = a real emoji sequence
# and must survive. A ZWJ next to ASCII, or at a string boundary, is an
# injected invisible and is removed.
_ZWJ = "‍"
_ZWJ_REMOVE_RE = re.compile(
    r"(?:(?<=[\x00-\x7f])‍)"   # ASCII before ZWJ
    r"|(?:‍(?=[\x00-\x7f]))"   # ASCII after ZWJ
    r"|^‍"                      # leading
    r"|‍$"                      # trailing
)


def strip_invisibles(text: str) -> str:
    """Remove zero-width and control characters from *text*.

    Strips zero-width spaces, word joiners, BOM, soft hyphens, bidi marks and
    isolates, invisible math operators, and C0/C1 control characters — while
    keeping ordinary tab/newline/carriage-return whitespace.

    Zero-width joiners that bind an emoji sequence (between two non-ASCII
    characters) are preserved; ZWJs adjacent to ASCII or at a string edge are
    removed. Returns the input unchanged when it holds none of these; never
    raises.
    """
    if not isinstance(text, str):
        return text
    try:
        # Context-sensitive ZWJ handling first (translate can't see neighbours).
        text = _ZWJ_REMOVE_RE.sub("", text)
        return text.translate(_INVISIBLE_TRANSLATE)
    except Exception:
        return text


# ---------------------------------------------------------------------------
# normalize_typography
# ---------------------------------------------------------------------------

_QUOTE_MAP = {
    0x201C: '"', 0x201D: '"', 0x201E: '"', 0x201F: '"',   # “ ” „ ‟
    0x2033: '"', 0x2036: '"',                              # ″ ‶ (double prime)
    0x2018: "'", 0x2019: "'", 0x201A: "'", 0x201B: "'",   # ‘ ’ ‚ ‛
    0x2032: "'", 0x2035: "'",                              # ′ ‵ (prime)
}

_DASH_MAP = {
    0x2010: "-", 0x2011: "-", 0x2012: "-", 0x2013: "-",   # hyphen..en dash
    0x2014: "-", 0x2015: "-",                             # em dash, horiz bar
    0x2212: "-",                                          # minus sign
}

_ELLIPSIS_MAP = {0x2026: "..."}   # …

# Non-breaking and exotic spaces → plain space.
_SPACE_MAP = {cp: " " for cp in [
    0x00A0,            # no-break space
    0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007,
    0x2008, 0x2009, 0x200A,        # en quad .. hair space
    0x202F,            # narrow no-break space
    0x205F,            # medium mathematical space
    0x3000,            # ideographic space
]}

_LIGATURE_MAP = {
    0xFB00: "ff", 0xFB01: "fi", 0xFB02: "fl",
    0xFB03: "ffi", 0xFB04: "ffl", 0xFB05: "ft", 0xFB06: "st",
}


def _build_fullwidth_map() -> dict:
    """Fullwidth ASCII variants (U+FF01..U+FF5E) map to their ASCII form by a
    fixed 0xFEE0 offset; the ideographic space maps to a normal space."""
    m = {cp: chr(cp - 0xFEE0) for cp in range(0xFF01, 0xFF5F)}
    m[0x3000] = " "
    return m


_FULLWIDTH_MAP = _build_fullwidth_map()


def normalize_typography(
    text: str,
    *,
    quotes: bool = True,
    dashes: bool = True,
    ellipsis: bool = True,
    spaces: bool = True,
    ligatures: bool = True,
    fullwidth: bool = False,
) -> str:
    """Map typographic Unicode punctuation in *text* to plain ASCII.

    Each category is an independent flag so callers keep what they want.
    ``quotes``, ``dashes``, ``ellipsis``, ``spaces`` and ``ligatures`` default
    on; ``fullwidth`` is **off by default** because fullwidth forms are usually
    genuine CJK-context characters, not noise.

    Note that ``dashes`` is lossy — every dash variant (including em dash)
    collapses to a single hyphen-minus — so disable it when dash distinctions
    matter. Returns the input unchanged when no category matches; never raises.

    Parameters
    ----------
    text:
        Raw model output (typically pasted/piped cloud-model prose).
    quotes, dashes, ellipsis, spaces, ligatures, fullwidth:
        Toggle each normalization category.
    """
    if not isinstance(text, str):
        return text
    try:
        table = {}
        if quotes:
            table.update(_QUOTE_MAP)
        if dashes:
            table.update(_DASH_MAP)
        if ellipsis:
            table.update(_ELLIPSIS_MAP)
        if spaces:
            table.update(_SPACE_MAP)
        if ligatures:
            table.update(_LIGATURE_MAP)
        if fullwidth:
            table.update(_FULLWIDTH_MAP)
        if not table:
            return text
        return text.translate(table)
    except Exception:
        return text
