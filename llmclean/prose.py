"""
prose.py — strip conversational scaffolding from free-text LLM output.

Two recurring nuisances when you ask a model for a plain answer and get back
chatter wrapped around it:

  1. Reasoning traces.  Reasoning-tuned models (DeepSeek-R1, QwQ, and anything
     prompted to "think first") emit a ``<think>...</think>`` block before the
     real answer.  Because the opening ``<think>`` often lives in the chat
     template, the API frequently returns only a *trailing* ``</think>`` with
     the trace in front of it and no opening tag at all.

  2. Conversational preamble / postamble.  "Sure! Here's the answer:" on the
     front, "Hope that helps! Let me know if you need anything else." on the
     back.  Harmless to a human, noise to a downstream parser.

``strip_reasoning_trace`` and ``strip_preamble`` remove these.  Both are
conservative — they only touch text matching known scaffolding shapes and
return the input unchanged (never raising) when nothing matches.

These operate on prose.  For JSON specifically, ``enforce_json`` already finds
the object inside surrounding chatter; reach for these when the payload you
want is itself free text.
"""

import re

# ---------------------------------------------------------------------------
# Reasoning traces
# ---------------------------------------------------------------------------

# Tag names models use to wrap chain-of-thought. Matched case-insensitively.
_REASONING_TAGS = (
    "think", "thinking", "thought", "thoughts",
    "scratchpad", "reflection", "reasoning", "rationale",
)

_TAG_ALT = "|".join(_REASONING_TAGS)

# A complete paired block: <think> ... </think>  (DOTALL so it spans newlines).
_PAIRED_TRACE_RE = re.compile(
    rf"<\s*(?P<tag>{_TAG_ALT})\s*>.*?<\s*/\s*(?P=tag)\s*>",
    re.IGNORECASE | re.DOTALL,
)

# A lone *closing* tag with no matching opener — the DeepSeek-R1 case where the
# opening tag came from the chat template. Everything from the start of the
# string up to and including this close tag is the trace.
_LONE_CLOSE_RE = re.compile(
    rf"^\s*(?P<lead>.*?)<\s*/\s*(?:{_TAG_ALT})\s*>",
    re.IGNORECASE | re.DOTALL,
)

# Any stray reasoning tag left over (e.g. an unclosed opener at the very top).
_ANY_TAG_RE = re.compile(
    rf"<\s*/?\s*(?:{_TAG_ALT})\s*>",
    re.IGNORECASE,
)


def strip_reasoning_trace(text: str) -> str:
    """Remove chain-of-thought reasoning blocks from *text*.

    Handles three shapes, in order:
      * paired tags — ``<think>...</think>`` (any tag in ``_REASONING_TAGS``);
      * a lone trailing close tag — ``...trace...</think>answer`` with no
        opener, the common DeepSeek-R1 API shape;
      * any orphaned reasoning tag left behind.

    Returns the answer text with surrounding whitespace collapsed.  If no
    reasoning markers are present the input is returned unchanged.  Never
    raises.
    """
    if not isinstance(text, str):
        return text

    original = text
    try:
        # 1. Remove fully-paired blocks first.
        text = _PAIRED_TRACE_RE.sub("", text)

        # 2. If a lone closing tag remains (opener was in the template), drop
        #    everything up to and including it — but only when there is no
        #    surviving opening tag in front of it, so we don't eat real content
        #    between a malformed open/close pair.
        m = _LONE_CLOSE_RE.search(text)
        if m and not re.search(rf"<\s*(?:{_TAG_ALT})\s*>", m.group("lead"),
                               re.IGNORECASE):
            text = text[m.end():]

        # 3. Sweep any orphaned tags (unclosed opener at the top, stray close).
        text = _ANY_TAG_RE.sub("", text)

        cleaned = text.strip()
        # Guard: if we stripped the whole thing to nothing, the input was
        # almost certainly a pure (possibly truncated) trace — return empty
        # only if the original genuinely had a reasoning tag, else restore.
        if not cleaned and not _ANY_TAG_RE.search(original) \
                and "</" not in original:
            return original
        return cleaned
    except Exception:
        return original


# ---------------------------------------------------------------------------
# Preamble / postamble
# ---------------------------------------------------------------------------

# Leading conversational filler — ONE filler unit, anchored at the start. The
# two kinds are kept separate so each is self-terminating:
#   A. interjections ("Sure!", "Certainly.", "Of course,") — the opener word
#      plus its own trailing punctuation IS the whole unit;
#   B. lead-ins that run to a colon ("Here is the answer:", "Below is …:").
# Applied repeatedly by strip_preamble so "Sure! Here is X: payload" peels both
# layers. Curated opener set so genuine content beginning with these words is
# rarely matched (e.g. "Heretical ideas…" never matches the "here is/are/'s"
# form, and "Certainly" only matches when it is its own clause).
_PREAMBLE_RE = re.compile(
    r"""^\s*
    (?:
        (?:                       # --- A: self-terminating interjection ---
            sure          | certainly   | of\ course | absolutely |
            no\ problem   | great       | okay       | ok         |
            as\ requested
        )
        \s*[!,.:]+\s*             # its own punctuation ends the unit
      |
        (?:                       # --- B: lead-in that runs to a colon ---
            here(?:\ is|\ are|'s) | below\ is | i'd\ be\ happy\ to |
            i\ can\ help          | let\ me
        )
        [^\n:]*:\s*               # ...up to and including the colon
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Trailing conversational filler. Anchored at the end of the text.
_POSTAMBLE_RE = re.compile(
    r"""
    \s*
    (?:                       # a recognised closing flourish...
        (?:i\ )?hope\ (?:this|that|it)\ helps    |
        let\ me\ know\ if                         |
        feel\ free\ to                            |
        please\ let\ me\ know                     |
        if\ you\ (?:have|need)\ any
    )
    [^\n]*                    # ...to the end of its line
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def strip_preamble(text: str, postamble: bool = True) -> str:
    """Remove leading (and optionally trailing) conversational filler.

    Strips a single recognised lead-in clause — "Sure!", "Here is the …:",
    "Certainly," and friends — from the front of *text*, and by default a
    closing flourish ("Hope that helps!", "Let me know if …") from the end.

    Only curated filler shapes are removed, so content that legitimately begins
    with one of these words but does not match the full opener pattern is left
    alone.  Returns the input unchanged when nothing matches; never raises.

    Parameters
    ----------
    text:
        Raw model output whose real payload is free text.
    postamble:
        When True (default) also strip a trailing closing flourish.
    """
    if not isinstance(text, str):
        return text

    original = text
    try:
        # Peel filler units one at a time: "Sure! Here is X:" needs two passes.
        for _ in range(3):
            new = _PREAMBLE_RE.sub("", text, count=1)
            if new == text:
                break
            text = new
        if postamble:
            text = _POSTAMBLE_RE.sub("", text, count=1)
        cleaned = text.strip()
        # Never strip the entire message away — if filler was all there was,
        # the caller is better served by the original than by an empty string.
        return cleaned if cleaned else original
    except Exception:
        return original
