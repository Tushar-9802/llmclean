# Changelog

## 0.3.0 — unreleased

Five new public functions and a correctness fix, grounded in an empirical sweep
of five local models (llama3.1 / gemma4 / qwen2.5 / deepseek-r1 / mistral, all
7–8B instruct) plus a survey of where the ecosystem already re-implements these
by hand.

### `enforce_json` — Python-literal fix no longer corrupts string content

`_replace_python_literals` did a blind `re.sub` of `True` / `False` / `None`,
despite its docstring claiming it only operated outside strings. It rewrote
those words everywhere — including inside string *values* (`{"note": "set to
True"}` → `…to true`) and string *keys* (`{"None": 1}` → `{null: 1}`). A regex
can't tell a bare literal token from the same letters inside quoted content, so
the fix is a single state-aware pass that tracks double/single-string context
(with escape handling) and rewrites literals and quote delimiters only outside
strings. Removed the now-dead `_single_to_double_quotes` helper and
`_PYTHON_LITERAL_RE`.

### `strip_reasoning_trace`, `strip_preamble` (new module `prose.py`)

`strip_reasoning_trace` removes `<think>…</think>` chain-of-thought blocks
(tags: think/thinking/thought/scratchpad/reflection/reasoning/rationale),
including the DeepSeek-R1 shape where the opener lived in the chat template and
only a trailing `</think>` is returned. `strip_preamble` removes curated
conversational filler — "Sure!", "Here is the …:", "Hope that helps!".

Scope finding worth recording: current Ollama (0.30.10) splits reasoning into a
separate `thinking`/`reasoning` field on both `/api/generate` and `/v1`, so its
native consumers never see the tags inline. `strip_reasoning_trace` is for the
backends that *do* inline them — llama.cpp direct, vLLM without
`--reasoning-parser`, TGI/SGLang, LM Studio, raw `transformers`, and most
aggregators. Validated against a real deepseek-r1 trace re-wrapped in that
inline wire format.

### `strip_invisibles`, `normalize_typography` (new module `unicode_norm.py`)

`strip_invisibles` removes zero-width spaces, word joiners, BOM, soft hyphens,
bidi marks/isolates, invisible math operators, and C0/C1 controls — keeping
tab/newline/CR, and preserving zero-width joiners that bind emoji sequences
(👨‍👩‍👧). `normalize_typography` maps smart quotes, em/en dashes, the ellipsis
character, non-breaking and exotic spaces, and ligatures to ASCII, with
per-category flags (a `fullwidth` category is opt-in, off by default).

Honest scope: across 40 generations the five local models emitted ASCII
punctuation *exclusively* — zero smart quotes, ellipsis chars, NBSP, ligatures,
or zero-width characters, even when explicitly prompted for them. This mess is a
frontier cloud-model trait (the em-dash complaints that made OpenAI ship a
toggle), so these two functions serve pasted/piped ChatGPT/Claude/Gemini output
and are tested against synthetic fixtures of that shape rather than local
output. Fullwidth punctuation *did* appear locally — but only in CJK prose,
never in JSON structure — which is why it is a normalize_typography category and
not a JSON-repair strategy.

### `strip_markdown` (new module `markdown.py`)

Flattens markdown to plain prose for the TTS / voice-bot / plain-field use case:
headers, bold/italic/strikethrough, inline code, links and images, blockquotes,
ordered/unordered lists, horizontal rules, and basic pipe tables; reuses
`strip_fences` for code blocks. Best-effort and conservative — `snake_case`
identifiers and `a-b` ranges survive because list/emphasis rules require markup
at a line start or span boundary. Markdown was the most common output trait in
the local baseline (every "explain with headers", code, and table prompt), so
this is validated against a real gemma4 capture.

### Tests

Suite grew from 78 to 138. The empirical harness lives in `dev/`
(`probe_models.py`, `probe_generative.py`) and writes gitignored JSONL captures;
the real-output fixtures in the prose/markdown tests come from those runs.

---

## 0.2.0 — 2026-05-11

### `strip_fences`

CRLF line endings were silently breaking fence detection on Windows. The closing-fence regex used `[ \t]*$` to anchor end-of-line. In `re.MULTILINE` mode, Python's `$` matches the position just before `\n`, not before `\r\n`. So on a line ending `` ` `` ` `` ` ``\r\n`, the cursor never reached `$` because `\r` sat between the trailing-whitespace class and the newline. The opening regex had the same bug.

The failure mode was inverted, which is what made it nasty: when both opener and closer had CRLF endings, only the *closing* line happened to match the regex (nothing after the fence chars). So the function read the closer as an unclosed *opener*, dropped that line, and kept the actual opener as content. Output looked like garbled JSON inside a leftover code fence.

Fix: `[ \t]*\r?$` in three places (open, close, lone-language-tag). Caught while running `strip_fences` on Ollama output captured from a Windows client.

Also picked up `lstrip("﻿")` at the entry point. Without it, a BOM right before the opening fence breaks the `^` anchor and no fence gets recognized at all.

### `enforce_json`

Strip BOM up-front. Files round-tripped through Windows IO or some LLM client SDKs prepend `U+FEFF`. `json.loads` sees that as "Unexpected character at position 0" and fails before any of the strategy pipeline runs. Same fix as Sakhi's `_parse_json_response`.

New strategy: collapse doubled-quote overruns like `""value""` to `"value"`. This shows up when an escape sequence leaks through upstream — a Python triple-quoted f-string somewhere in the chain, or a model that double-escaped. Sakhi has two more variants for this (`: ""x` and `x""`) but those corrupt legitimate empty-string values like `{"k": ""}` because the regex can't tell "overrun" from "intentional empty". I only included the content-required form, which is unambiguous.

Cleanup: removed duplicated `_parse_and_serialize` and Python-literal helpers at the end of `json_utils.py`. Python lets the second definition silently overwrite the first, so runtime behaviour was unchanged, but the duplication was visible on inspection — leftover from an earlier refactor that didn't fully tidy up.

### Tests

Suite grew from 32 to 78. New coverage worth calling out:

- CRLF / LF equivalence for `strip_fences` (full CRLF, mixed line endings, unclosed CRLF)
- Closing-fence length rules: close longer than open works, close shorter than open doesn't
- Mixed fence types (backtick + tilde) — characterization test for the aggressive-cleanup interpretation
- `strip_fences` idempotency over 7 inputs (parametrized property test)
- The known false-positive: a single-word answer like `` ` `` ` `` ` ``\njson\n`` ` `` ` `` ` `` strips to empty. Documented limitation, locked in by the test so a future "fix" can't silently regress fence cleanup on common inputs.
- BOM stripping for both `strip_fences` and `enforce_json`
- Double-quote collapse with explicit tests that `""` (legitimate empty) survives both as object value and array element

### Provenance

Almost everything in this release came from looking at how my other projects ([Sakhi](https://github.com/Tushar-9802/Sakhi), [Resume-parser](https://github.com/Tushar-9802/Resume-parser)) had been quietly working around llmclean's gaps. The CHANGELOG is essentially "what production traffic taught me, brought back upstream."

---

## 0.1.0 — 2026-03-09

Initial release. Three utilities: `strip_fences`, `enforce_json`, `trim_repetition`. Zero runtime dependencies.
