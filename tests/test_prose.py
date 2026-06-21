"""Tests for llmclean.prose — reasoning-trace and preamble stripping.

Fixtures marked REAL are verbatim captures from local Ollama models
(qwen2.5:7b-instruct, gemma4:e4b-it-q4_K_M) via dev/probe_models.py, so the
behaviour is validated against real output, not only hand-written shapes.
"""

from llmclean import strip_reasoning_trace, strip_preamble


# ---------------------------------------------------------------------------
# strip_reasoning_trace
# ---------------------------------------------------------------------------

def test_paired_think_block_removed():
    text = "<think>let me work this out, 2+2=4</think>\nThe answer is 4."
    assert strip_reasoning_trace(text) == "The answer is 4."


def test_paired_block_spanning_newlines():
    text = "<thinking>\nstep 1\nstep 2\n</thinking>\nDone."
    assert strip_reasoning_trace(text) == "Done."


def test_lone_trailing_close_tag_deepseek_shape():
    # DeepSeek-R1 API shape: opener lived in the template, only </think> returns.
    text = "Okay, the user wants the capital. It is Paris.</think>\n\nParis."
    assert strip_reasoning_trace(text) == "Paris."


def test_multiple_tag_kinds():
    text = "<reasoning>a</reasoning><scratchpad>b</scratchpad>real answer"
    assert strip_reasoning_trace(text) == "real answer"


def test_case_and_whitespace_insensitive_tags():
    text = "< Think >noise</ THINK >answer"
    assert strip_reasoning_trace(text) == "answer"


def test_no_reasoning_marker_returned_unchanged():
    text = "Just a normal answer with no tags."
    assert strip_reasoning_trace(text) == text


def test_does_not_eat_content_between_real_open_and_close():
    # A genuine open+close pair is a paired block and goes entirely; content
    # after it survives.
    text = "<think>x</think>keep this"
    assert strip_reasoning_trace(text) == "keep this"


def test_non_string_passthrough():
    assert strip_reasoning_trace(None) is None
    assert strip_reasoning_trace(42) == 42


# ---------------------------------------------------------------------------
# strip_preamble
# ---------------------------------------------------------------------------

def test_sure_heres_preamble():
    text = "Sure! Here is the answer: 42"
    assert strip_preamble(text) == "42"


def test_certainly_preamble():
    text = "Certainly. The capital of France is Paris."
    assert strip_preamble(text) == "The capital of France is Paris."


def test_postamble_removed():
    text = "The result is 7.\n\nHope that helps! Let me know if you need anything else."
    assert strip_preamble(text) == "The result is 7."


def test_postamble_can_be_disabled():
    text = "Answer: 7. Hope this helps!"
    out = strip_preamble(text, postamble=False)
    assert out.endswith("Hope this helps!")


def test_content_starting_with_word_but_not_filler_pattern_kept():
    # "Here" appears but not as a filler opener clause — left intact.
    text = "Heretical ideas were common in that era."
    assert strip_preamble(text) == text


def test_preamble_never_strips_everything():
    # If filler is all there is, return the original rather than empty string.
    text = "Sure!"
    assert strip_preamble(text) == text


def test_non_string_passthrough_preamble():
    assert strip_preamble(None) is None


# ---------------------------------------------------------------------------
# REAL captures + the honest scope boundary.
#
# qwen2.5's reason_first output leads with multi-paragraph REASONING
# ("Let's break down...") — not conversational filler. strip_preamble is
# deliberately conservative: it only removes recognised filler shapes, so it
# leaves arbitrary reasoning prose ALONE (eating it would risk real content).
# Extracting the JSON payload out of that reasoning is enforce_json's job, not
# strip_preamble's. This test pins that boundary so the scope stays honest.
# ---------------------------------------------------------------------------

REAL_QWEN_REASON_FIRST = (
    'Let\'s break down the given text "The order shipped on Tuesday for $42" '
    "step-by-step:\n\n1. Identify Key Information.\n\n"
    "Here is the JSON representation:\n\n"
    '```json\n{\n  "order_status": "shipped"\n}\n```'
)


def test_real_qwen_reasoning_preamble_is_left_alone():
    # Reasoning preamble is not filler — strip_preamble must not touch it.
    assert strip_preamble(REAL_QWEN_REASON_FIRST) == REAL_QWEN_REASON_FIRST.strip()


def test_real_style_filler_wrapper_is_stripped():
    # The filler shapes strip_preamble DOES target, in a realistic wrapper.
    text = "Sure! Here is the JSON you asked for: {\"ok\": true}"
    assert strip_preamble(text) == '{"ok": true}'


# ---------------------------------------------------------------------------
# REAL deepseek-r1:7b reasoning trace.
#
# Current Ollama splits <think> into a separate `thinking` field, so its native
# API consumers never see the tags. But llama.cpp direct, vLLM without a
# reasoning-parser, raw transformers, LM Studio, and most aggregators emit the
# tags INLINE in the content. The fixture below is the verbatim `thinking`
# field captured from deepseek-r1:7b, re-wrapped in the exact inline wire format
# those non-Ollama backends produce — so the stripper is validated against a
# genuine trace, not a hand-written one.
# ---------------------------------------------------------------------------

# Verbatim opening of a real deepseek-r1:7b `thinking` field (Is 17 prime?).
_REAL_DS_THINK = (
    "Okay, so I need to figure out if 17 is a prime number or not. Hmm, "
    "let's start by recalling what a prime number is. A prime number is a "
    "natural number greater than 1 that has no positive divisors other than "
    "1 and itself."
)
_REAL_DS_ANSWER = "Yes, 17 is a prime number."


def test_real_trace_paired_tags_inline_wire_format():
    # vLLM / llama.cpp / transformers shape: <think>...</think> inline.
    wire = f"<think>{_REAL_DS_THINK}</think>\n\n{_REAL_DS_ANSWER}"
    assert strip_reasoning_trace(wire) == _REAL_DS_ANSWER


def test_real_trace_lone_trailing_close_deepseek_template_shape():
    # DeepSeek template shape: opener consumed upstream, only </think> remains.
    wire = f"{_REAL_DS_THINK}</think>\n\n{_REAL_DS_ANSWER}"
    assert strip_reasoning_trace(wire) == _REAL_DS_ANSWER
