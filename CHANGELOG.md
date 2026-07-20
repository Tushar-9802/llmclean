# Changelog

## 0.4.0 — unreleased

Degeneration detection, from a study of 24 fine-tuned model variants (~600 generations per eval) plus controlled decode probes. Also a front door, because the library had grown to fifteen functions with no obvious place to start.

### Fixed: truncation detection flagged all non-Latin output

`looks_truncated` checked the final character against a Latin-only terminator set, so any language that does not end sentences with `.`/`!`/`?` was reported as cut off mid-thought. Measured on a multilingual corpus: **100% of Hindi output** (which ends with the danda `।`) and **100% of Chinese output** (ideographic full stop `。`) were falsely flagged.

The terminator set now covers Devanagari (`।` `॥`), CJK (`。` `！` `？` `．` and closing quotes/brackets), Urdu/Arabic (`۔` `؟`), Khmer, and Ethiopic. A closing code fence is also treated as a structural end rather than a truncation.

Effect on a 269-text corpus: false truncation flags fell from 66% to 27% of non-capped generations, while deliberately token-capped generations stayed at 85% — the remaining flags are genuine (output ending mid-word, or mid-fence with `` `` `` instead of ```` ``` ````). Chinese went from 12/12 flagged to 0/12.

Found by replaying a generated production corpus rather than by unit tests, which is the point of the harness below.

### Validation: a production-shaped corpus

`dev/simulate_production.py` generates output from five local models across fifteen task types (flat/nested/array JSON, JSON from long context, chat, summarization, markdown, code, classification, Hindi, Chinese, Hinglish code-switching, user-JSON echo, tables) and four decode conditions including a 24-token cap that forces real truncation. Each generation is then replayed through eight transport mutations that model what happens between a model and a parser: CRLF from Windows clients, BOM from gateways, mid-stream cutoff, HTML escaping, UTF-8-decoded-as-latin-1 mojibake, duplicated stream-chunk boundaries, trailing whitespace.

300 generations, 269 non-empty texts, 8 mutations, 14 functions: **30,128 calls, zero escaped exceptions, zero internal warnings.** JSON extraction tasks parsed to a dict 90% of the time under normal decode conditions (100% for llama3.1, mistral, and qwen2.5) and 25% under the 24-token cap, which is the correct outcome — JSON cut off at 24 tokens is not recoverable.

### New: the never-raise guarantee stopped hiding bugs

Thirteen defensive `except Exception` blocks kept the never-raise contract by returning the input unchanged — and swallowed every internal error with no trace. An injected bug in `strip_markdown` returned `'# Title'` and printed nothing, even with `logging.basicConfig(level=DEBUG)`. That is the same failure the library's own `degeneracy.py` warns about: a cleaner that silently tidies the overflow hides the damage.

Every fallback now logs to a `logging.getLogger("llmclean")` with a `NullHandler` — silent unless the application configures logging. Unexpected exceptions log at `WARNING` with `exc_info`; expected misses (no JSON in the text) log at `DEBUG`. `enable_debug_logging()` is an opt-in one-liner for a quick look. The log helpers swallow their own errors, so a misconfigured handler cannot become the thing that raises.

Validated across 784 calls — 86 real outputs from llama3.1/gemma4/qwen2.5/deepseek-r1/mistral plus 12 hostile inputs (empty, null bytes, 20k-word strings, 300-deep nesting, lone surrogates, RTL overrides, emoji ZWJ sequences) — with zero escaped exceptions and zero internal warnings.

### New: three front doors

```python
data   = llmclean.load_json(raw)    # → dict/list, or None
text   = llmclean.clean_text(raw)   # → clean plain prose
report = llmclean.check(raw)        # → degeneration report
```

The common case was four lines and a `try/except`: `enforce_json` returns a *string*, so every caller then had to `json.loads` it themselves and handle the failure. `load_json` does the whole thing and returns the parsed object or your `default`. It strips reasoning traces before extraction, so braces inside a `<think>` block can't hijack the result.

`clean_text` composes reasoning-trace → preamble → markdown → invisibles → typography, each toggleable. Repetition trimming is off by default: doing it silently would hide the model damage `check` exists to surface.

The dozen single-purpose functions are unchanged and remain exported for callers who want to control the pipeline.

### The gap this closes

Repetition happens at three levels and `trim_repetition` only covered one. Verified against v0.3.0:

| level | example | v0.3.0 |
|---|---|---|
| phrase | `"So this is 8 infinity. So this is 8 infinity."` | handled |
| token | `"parameter parameter parameter"` | **missed** |
| subword | `"thresholdinginginging"` | **missed** |

The n-gram strategy's smallest visible unit is a 5-word phrase occurring 3 times, so a 1-word phrase occurring 3 times is invisible. Token and subword loops are also scattered through the text rather than tail-concentrated, so a tail-trimmer cannot reach them regardless.

### New: `degeneracy_score` (detection as a first-class API)

Reports without modifying. `degenerate` is the OR of five calibrated rules — `distinct_ratio`, `top_token_frac`, `adjacent_dup_rate`, `intra_word_rate`, and `phrase_repetition` (which reuses `trim_repetition`). The rules overlap but none is redundant: the subword sample passes all four word-level rules because it is a single unique word; total collapse passes the subword rule; phrase loops pass all four word-level rules because their words alternate.

`truncated` and `mixed_script_words` are reported but excluded from the verdict — separate axes with separate fixes. Truncation is a token-budget problem; conflating it with repetition buries a real signal (in the source study a healthy model was 9% truncated and a damaged one 41%).

Thresholds: 0 false positives across ~675 clean texts, 15/15 true positives on known-bad masked output. `short_text` flags input under 30 words where the rates get noisy.

### New: repair functions

`collapse_word_runs` collapses runs of 3+ identical adjacent words; runs of 2 are left alone because they occur in real English ("had had", "that that"). `collapse_intra_word_runs` is opt-in and lossy — it iterates to a fixpoint since one pass leaves residue, and it will also collapse genuine reduplication ("couscous"). A tripped `intra_word_rate` usually means the generation should be retried, not repaired.

Also `adjacent_dup_rate`, `intra_word_rate`, `looks_truncated`, and `mixed_script_words` as individual signals. Word-internal script mixing catches intrusions like `"ReLУ"` (Cyrillic У in a Latin word); it never inspects beyond a single word, because document-level script mixing is legitimate in Hinglish and any bilingual text.

### Decode-probe finding: run length is mechanism-dependent

The source study measured HF's `no_repeat_ngram_size`, a hard trigram ban, which truncates an unbounded `X X X X…` loop at exactly the fourth `X` — so masked traffic shows exactly-three runs and never longer.

llama.cpp/Ollama use `repeat_penalty`, a soft logit penalty, and it does not behave that way. Across 50 generations (5 models × 2 conditions × 5 loop-inviting prompts, greedy decode): with the penalty at its default the longest adjacent run was 1, and with it disabled gemma4 produced a **61-word** run (`"superb, superb, superb…"` to the token budget) rather than anything truncated to 3. Detection therefore collapses at >=3 and does not tune for a specific run length.

Two more things that sweep showed: disabling the penalty roughly doubled the degeneration rate (3/25 → 6/25), and across all 50 generations from stock instruct models, phrase-level repetition dominated, token loops appeared once, and subword loops never appeared at all. The token and subword modes are fine-tune damage signatures, not stock-model behaviour — which is consistent with the source study, where they came from a mis-designed auxiliary training loss.

---

## 0.3.0 — 2026-06-21

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
