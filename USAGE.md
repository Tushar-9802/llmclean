# llmclean — Usage Guide

Full examples for every function with real inputs and outputs you can paste and run.

```bash
cd llmclean
python3
>>> from llmclean import strip_fences, enforce_json, trim_repetition
>>> from llmclean import strip_reasoning_trace, strip_preamble
>>> from llmclean import strip_invisibles, normalize_typography, strip_markdown
```

---

## Start here: the three front doors

Most callers never need anything below this section.

```python
import llmclean

# 1. I asked for JSON — give me a dict
llmclean.load_json('Sure!\n```json\n{"ok": True, "n": [1,2,3,]}\n```')
# → {'ok': True, 'n': [1, 2, 3]}
llmclean.load_json('no json here')          # → None
llmclean.load_json('nope', default={})      # → {}

# 2. I asked for prose — give me clean text
llmclean.clean_text('<think>hmm</think>Sure! Here is the answer:\n\n# Title\n\n- **bold** point')
# → 'Title\n\nbold point'

# 3. Is this output broken?
llmclean.check('We tune the parameter parameter parameter values today.')
# → {'degenerate': True, 'rules_fired': ['top_token_frac', 'adjacent_dup_rate'], ...}
```

`load_json` strips reasoning traces first (so braces inside a `<think>` block can't hijack extraction), then runs the full `enforce_json` repair pipeline and parses. Returns `default` instead of raising.

`clean_text` runs: reasoning trace → conversational filler → markdown → invisible characters → typography. Each stage is a keyword flag:

```python
llmclean.clean_text(raw, markdown=False)       # keep the markdown
llmclean.clean_text(raw, typography=False)     # keep smart quotes / em dashes
llmclean.clean_text(raw, repetition=True)      # also trim repeated tails (off by default)
```

`repetition` is off by default on purpose: silently trimming it would hide model damage, which is exactly what `check` exists to surface.

---

**The lower-level functions by job:**

| Function | Cleans up |
|---|---|
| `strip_fences` | ` ``` ` / `~~~` code-fence wrappers |
| `enforce_json` | malformed / prose-wrapped JSON |
| `trim_repetition` | degenerate repeated tail content |
| `strip_reasoning_trace` | `<think>…</think>` chain-of-thought blocks |
| `strip_preamble` | "Sure! Here's…" / "Hope that helps!" filler |
| `strip_invisibles` | zero-width & control characters |
| `normalize_typography` | smart quotes / em dashes / ellipsis → ASCII |
| `strip_markdown` | markdown formatting → plain prose |
| `degeneracy_score` | reports token/subword/phrase loops (does not modify) |
| `collapse_word_runs` | runs of 3+ identical adjacent words |
| `collapse_intra_word_runs` | repeated substrings inside a word (opt-in, lossy) |

---

## `strip_fences(text)`

Removes the ` ``` ` or `~~~` wrapper that LLMs put around code and data. Preserves everything outside the fence. Returns the original unchanged if there are no fences.

```python
from llmclean import strip_fences

# Named fence — most common case
strip_fences('```json\n{"name": "Alice"}\n```')
# → '{"name": "Alice"}'

# Python fence
strip_fences('```python\nprint("hello")\n```')
# → 'print("hello")'

# Anonymous fence (no language tag)
strip_fences('```\nhello world\n```')
# → 'hello world'

# Tilde fence
strip_fences('~~~yaml\nkey: value\n~~~')
# → 'key: value'

# Prose before and after — both preserved
strip_fences('Here is the result:\n```json\n{"x":1}\n```\nHope that helps!')
# → 'Here is the result:\n{"x":1}\nHope that helps!'

# Multiple fences in one string — all stripped
strip_fences('```json\n{"a":1}\n```\n\n```python\nx=2\n```')
# → '{"a":1}\n\nx=2'

# Unclosed fence — drops the opening line, keeps the rest
strip_fences('```python\nprint("hi")')
# → 'print("hi")'

# No fences — returned exactly unchanged
strip_fences('plain text with no fences')
# → 'plain text with no fences'

# Wrong type — does not crash
strip_fences(None)   # → None
strip_fences(42)     # → 42
```

---

## `enforce_json(text)`

Extracts valid JSON from messy LLM output. Tries 8 strategies in order and stops at the first one that works. If nothing works, returns the original text unchanged — it never throws. Output is always re-serialized with consistent 2-space indentation.

**Strategies in order:** parse as-is → strip fences → extract JSON substring from prose → collapse doubled-quote overruns (`""x""`) → fix trailing commas → fix Python literals → fix unquoted keys → close open brackets → all combined.

> Python-literal handling is **string-aware** (since 0.3.0): `True`/`False`/`None` are only converted when they appear as JSON *values*, never inside string content — `{"note": "set flag to True"}` keeps its `True`.

```python
from llmclean import enforce_json
import json

# 1. Already valid — re-serialized consistently
enforce_json('{"key": "value"}')
# → '{\n  "key": "value"\n}'

# 2. Fenced JSON
enforce_json('```json\n{"name": "Alice"}\n```')
# → '{\n  "name": "Alice"\n}'

# 3. JSON buried in prose
enforce_json('Sure! Here is your data: {"result": true} Let me know if you need more.')
# → '{\n  "result": true\n}'

# 4. Trailing commas — illegal in JSON, fixed automatically
enforce_json('{"a": 1, "b": 2,}')
# → '{\n  "a": 1,\n  "b": 2\n}'

enforce_json('[1, 2, 3,]')
# → '[\n  1,\n  2,\n  3\n]'

enforce_json('{"a": [1, 2,], "b": {"c": 3,},}')
# → '{\n  "a": [\n    1,\n    2\n  ],\n  "b": {\n    "c": 3\n  }\n}'

# 5. Python literals — LLMs output these constantly
enforce_json('{"active": True, "deleted": False, "alias": None}')
# → '{\n  "active": true,\n  "deleted": false,\n  "alias": null\n}'

enforce_json('[True, False, None, 42]')
# → '[\n  true,\n  false,\n  null,\n  42\n]'

# 6. Single-quoted strings — Python style, not valid JSON
enforce_json("{'name': 'Alice', 'age': 30}")
# → '{\n  "name": "Alice",\n  "age": 30\n}'

# 7. Unquoted keys
enforce_json('{name: "Alice", age: 30}')
# → '{\n  "name": "Alice",\n  "age": 30\n}'

# 8. Unclosed brackets
enforce_json('{"a": 1, "b": 2')
# → '{\n  "a": 1,\n  "b": 2\n}'

enforce_json('{"a": [1, 2')
# → '{\n  "a": [\n    1,\n    2\n  ]\n}'

# 9. Everything wrong at once
enforce_json('```json\n{"ok": True, "items": [1, 2, 3,],}\n```')
# → '{\n  "ok": true,\n  "items": [\n    1,\n    2,\n    3\n  ]\n}'

# 10. Genuinely not JSON — returns original unchanged
enforce_json('this is just a sentence')
# → 'this is just a sentence'

# 11. Wrong type — does not crash
enforce_json(None)   # → None
enforce_json(42)     # → 42
```

**Recommended pattern in production code:**

```python
result = enforce_json(raw_llm_output)
try:
    data = json.loads(result)
except json.JSONDecodeError:
    # enforce_json gave up and returned the original — handle failure here
    data = None
```

---

## `trim_repetition(text, *, similarity_threshold=0.82)`

Detects and removes repetitive content from the tail of LLM output. Only ever trims from the end — unique content at the start is always preserved. Returns the original unchanged if no repetition is found.

**Detection strategies in order:** exact sentence repeat → near-duplicate sentences (Jaccard similarity) → repeated n-gram phrases → repeated paragraphs.

```python
from llmclean import trim_repetition

# 1. Exact sentence repeated at the end — one copy kept
trim_repetition(
    "Paris is the capital of France. "
    "It is famous for the Eiffel Tower. "
    "It is famous for the Eiffel Tower."
)
# → 'Paris is the capital of France. It is famous for the Eiffel Tower.'

# 2. Three or more repeats — all copies after the first removed
trim_repetition(
    "The answer is 42. "
    "This is the final answer. "
    "This is the final answer. "
    "This is the final answer."
)
# → 'The answer is 42. This is the final answer.'

# 3. Unique intro always preserved
trim_repetition(
    "Introduction to the topic. "
    "First key point is important. "
    "Second key point builds on that. "
    "Second key point builds on that."
)
# → 'Introduction to the topic. First key point is important. Second key point builds on that.'

# 4. Near-duplicate sentences
#    Default threshold 0.82 — lower it to catch looser duplicates
trim_repetition(
    "The model outputs a JSON object with the results. "
    "The model outputs a JSON structure containing the results.",
    similarity_threshold=0.6
)
# → 'The model outputs a JSON object with the results.'

# 5. Repeated paragraphs
trim_repetition(
    "Opening paragraph with unique content.\n\n"
    "This is a repeated paragraph with enough length to matter.\n\n"
    "This is a repeated paragraph with enough length to matter."
)
# → 'Opening paragraph with unique content.\n\nThis is a repeated paragraph with enough length to matter.'

# 6. No repetition — returned exactly unchanged
t = "The quick brown fox jumps over the lazy dog."
trim_repetition(t) == t
# → True

# 7. Never returns empty string — always keeps at least one copy
trim_repetition("Hello. Hello. Hello.")
# → 'Hello.'

# 8. Wrong type — does not crash
trim_repetition(None)   # → None
```

**Tuning `similarity_threshold`:**

| Value | Behaviour |
|---|---|
| `0.99` | Only catches near-identical sentences (very conservative) |
| `0.82` | Default — catches clearly similar sentences |
| `0.6` | Catches loosely similar sentences (more aggressive) |
| `0.4` | Very aggressive — may trim sentences that aren't real duplicates |

---

## `strip_reasoning_trace(text)`

Removes chain-of-thought reasoning blocks that reasoning-tuned models emit before the real answer. Handles paired tags, the DeepSeek-R1 shape where only a trailing `</think>` survives, and orphaned tags. Returns the input unchanged when no reasoning markers are present; never throws.

Recognised tags (case- and whitespace-insensitive): `think`, `thinking`, `thought`, `thoughts`, `scratchpad`, `reflection`, `reasoning`, `rationale`.

```python
from llmclean import strip_reasoning_trace

# 1. Paired <think> block
strip_reasoning_trace("<think>let me work it out, 2+2=4</think>\nThe answer is 4.")
# → 'The answer is 4.'

# 2. Block spanning multiple lines
strip_reasoning_trace("<thinking>\nstep 1\nstep 2\n</thinking>\nDone.")
# → 'Done.'

# 3. DeepSeek-R1 shape — opener was in the chat template, only </think> returns
strip_reasoning_trace("Okay, the capital is Paris.</think>\n\nParis.")
# → 'Paris.'

# 4. Other tag kinds
strip_reasoning_trace("<reasoning>a</reasoning><scratchpad>b</scratchpad>real answer")
# → 'real answer'

# 5. No reasoning markers — returned unchanged
strip_reasoning_trace("Just a normal answer.")
# → 'Just a normal answer.'

# 6. Wrong type — does not crash
strip_reasoning_trace(None)   # → None
```

> **When you need this:** current Ollama splits reasoning into a separate `thinking` field, so its native API never inlines the tags. Reach for `strip_reasoning_trace` when consuming backends that *do* inline them — llama.cpp directly, vLLM without `--reasoning-parser`, TGI/SGLang, LM Studio, raw `transformers`, and most hosted aggregators.

---

## `strip_preamble(text, postamble=True)`

Removes leading conversational filler (and, by default, a trailing closing flourish). Only curated filler shapes are removed, so real content that merely begins with one of these words is left alone. Peels multiple layers ("Sure! Here is …:"). Never strips the message down to nothing; never throws.

```python
from llmclean import strip_preamble

# 1. "Sure! Here is …:" lead-in
strip_preamble("Sure! Here is the answer: 42")
# → '42'

# 2. "Certainly." interjection
strip_preamble("Certainly. The capital of France is Paris.")
# → 'The capital of France is Paris.'

# 3. Trailing flourish removed too
strip_preamble("The result is 7.\n\nHope that helps! Let me know if you need anything else.")
# → 'The result is 7.'

# 4. Keep the trailing flourish
strip_preamble("Answer: 7. Hope this helps!", postamble=False)
# → 'Answer: 7. Hope this helps!'

# 5. Not a filler pattern — left intact
strip_preamble("Heretical ideas were common in that era.")
# → 'Heretical ideas were common in that era.'

# 6. Wrong type — does not crash
strip_preamble(None)   # → None
```

> `strip_preamble` only removes recognised *conversational* filler. It deliberately leaves arbitrary reasoning preamble ("Let's break this down step by step…") alone — pulling a payload out of that is `enforce_json`'s job, not this one's.

---

## `strip_invisibles(text)`

Removes zero-width and control characters that are invisible yet silently break search, regex, tokenization, equality checks, and copy-paste. Keeps ordinary tab / newline / carriage-return whitespace. Preserves zero-width joiners that bind emoji sequences. Never throws.

Removes: zero-width space/non-joiner, word joiner, BOM, soft hyphen, bidi marks/isolates/overrides, invisible math operators, and C0/C1 control characters.

```python
from llmclean import strip_invisibles

# 1. Zero-width space injected mid-word + trailing BOM
strip_invisibles("hel​lo﻿")
# → 'hello'

# 2. Bidi marks
strip_invisibles("a‮b‬c")
# → 'abc'

# 3. Ordinary whitespace is preserved
strip_invisibles("a\tb\nc\rd")
# → 'a\tb\nc\rd'

# 4. Emoji ZWJ sequence is preserved (family emoji stays intact)
strip_invisibles("\U0001F468‍\U0001F469‍\U0001F467")
# → '👨‍👩‍👧'  (unchanged)

# 5. A ZWJ injected between ASCII letters (watermark trick) is removed
strip_invisibles("a‍b")
# → 'ab'

# 6. Wrong type — does not crash
strip_invisibles(None)   # → None
```

---

## `normalize_typography(text, *, quotes=True, dashes=True, ellipsis=True, spaces=True, ligatures=True, fullwidth=False)`

Maps "published-prose" Unicode punctuation to plain ASCII. Each category is an independent flag. `fullwidth` is **off by default** because fullwidth forms are usually genuine CJK-context characters. `snake_case` and ordinary ASCII are never touched. Never throws.

| Category | Maps | Default |
|---|---|---|
| `quotes` | `“ ” ‘ ’` → `" '` | on |
| `dashes` | `— – ― −` → `-` *(lossy)* | on |
| `ellipsis` | `…` → `...` | on |
| `spaces` | NBSP & exotic spaces → ` ` | on |
| `ligatures` | `ﬁ ﬂ ﬀ` → `fi fl ff` | on |
| `fullwidth` | `ｈｉ！` → `hi!` | **off** |

```python
from llmclean import normalize_typography

# 1. Smart quotes, em dash, ellipsis — the classic pasted-cloud-output mess
normalize_typography("“It’s fine”—really…")
# → '"It\'s fine"-really...'

# 2. Non-breaking and ideographic spaces → regular space
normalize_typography("a b　c")
# → 'a b c'

# 3. Ligatures expanded
normalize_typography("ﬁle ﬂow oﬃce")
# → 'file flow office'

# 4. snake_case and ASCII left exactly alone
normalize_typography("my_var = func_name(x)")
# → 'my_var = func_name(x)'

# 5. Disable a category — keep the dashes
normalize_typography("“hi”—x", dashes=False)
# → '"hi"—x'

# 6. Opt in to fullwidth normalization
normalize_typography("ｈｉ！", fullwidth=True)
# → 'hi!'

# 7. Wrong type — does not crash
normalize_typography(None)   # → None
```

> **When you need this:** local 7–8B models emit ASCII punctuation almost exclusively. This mess is overwhelmingly a frontier cloud-model trait (ChatGPT/Claude/Gemini) that reaches your pipeline when such output is pasted or piped in.

---

## `strip_markdown(text)`

Flattens markdown formatting to plain prose — for text-to-speech, voice/chat bots, SMS, and plain UI fields that should not read out "hashtag hashtag Introduction". Best-effort and conservative: `snake_case` identifiers and `a-b` ranges survive. Reuses `strip_fences` for code blocks. Never throws.

Handles: headers, bold/italic/strikethrough, inline code, links and images, blockquotes, ordered/unordered lists, horizontal rules, and basic pipe tables.

```python
from llmclean import strip_markdown

# 1. Header + bullet + bold + inline code
strip_markdown("# Title\n\n- **bold** point with `code`")
# → 'Title\n\nbold point with code'

# 2. Links keep the text, drop the URL
strip_markdown("see [the docs](https://example.com/x)")
# → 'see the docs'

# 3. Blockquote and ordered list
strip_markdown("> quoted line\n\n1. first\n2. second")
# → 'quoted line\n\nfirst\nsecond'

# 4. snake_case survives (underscore emphasis requires word boundaries)
strip_markdown("set my_flag_value to true")
# → 'set my_flag_value to true'

# 5. Pipe table flattened to readable cells
#    (the |---| separator row is dropped, leaving a blank line)
strip_markdown("| A | B |\n|---|---|\n| 1 | 2 |")
# → 'A  B\n\n1  2'

# 6. Wrong type — does not crash
strip_markdown(None)   # → None
```

---

## `degeneracy_score(text, cap_tokens=None)` and friends

Repetition happens at three levels, and `trim_repetition` only covers one:

| level | example | covered by |
|---|---|---|
| phrase (clause loops) | `"So this is 8 infinity. So this is 8 infinity."` | `trim_repetition` |
| token (adjacent words) | `"parameter parameter parameter"` | `collapse_word_runs` |
| subword (inside a word) | `"thresholdinginginging"` | `collapse_intra_word_runs` |

`degeneracy_score` reports all three plus vocabulary collapse, without modifying anything.

```python
from llmclean import degeneracy_score, collapse_word_runs, collapse_intra_word_runs

degeneracy_score("The encoder maps input tokens to dense vectors downstream.")
# → {'degenerate': False, 'rules_fired': [], ...}

degeneracy_score("We tune the parameter parameter parameter values today.")
# → {'degenerate': True, 'rules_fired': ['adjacent_dup_rate'], ...}

# The subword case is invisible to every word-level metric — one unique word
degeneracy_score("thresholdinginginging")
# → distinct_ratio 1.0, adjacent_dup_rate 0.0, but rules_fired ['intra_word_rate']

# Repair (only when you cannot regenerate)
collapse_word_runs("the parameter parameter parameter values")   # → 'the parameter values'
collapse_word_runs("the things that that he had had before")     # → unchanged (doubles are real English)
collapse_intra_word_runs("thresholdinginginging")                # → 'thresholding'
```

Returned keys: `degenerate`, `rules_fired`, `short_text`, `word_count`, `distinct_ratio`, `top_token_frac`, `adjacent_dup_rate`, `intra_word_rate`, `phrase_repetition`, `truncated`, `mixed_script_words`.

`truncated` and `mixed_script_words` are reported but excluded from the `degenerate` verdict — separate failure axes with separate fixes. Truncation is a token-budget/EOS problem, not a repetition problem; prefer your provider's `finish_reason` when you have it.

Thresholds are calibrated on English prose of roughly 100–250 words. On shorter text one repeated token swings the rates, so `short_text` is set below 30 words — treat a flag there as weak evidence.

### Decode-side context worth knowing

If you're reaching for `trim_repetition`, you may be fighting this one layer too late:

- Anti-repetition decode settings **mask** loops rather than fix them. Cleaned text looks better while the model stays broken, so log `degeneracy_score` even when cleaning succeeds.
- Run length depends on the mechanism, so don't tune for a specific length. A hard trigram ban (`no_repeat_ngram_size=3`) truncates unbounded loops into exactly-three runs. A soft logit penalty (llama.cpp/Ollama `repeat_penalty`) gives you either no runs at all or fully unbounded ones — measured here as a 61-word run from gemma4 at `repeat_penalty=1.0`.
- `repetition_penalty` is not free: at 1.15 it suppressed loops but visibly degraded content quality by over-penalizing legitimate reuse of topic words. Gentle values (≤1.05) plus detection is the safer combination.
- If a large fraction of outputs trip the detector, the model or its fine-tune is the problem. In the study behind these rules the cause was a mis-designed auxiliary training loss, and no amount of output cleaning was the right fix.

---

## Combining functions

The functions are independent and chain naturally.

```python
from llmclean import strip_fences, enforce_json, trim_repetition
from llmclean import strip_reasoning_trace, strip_preamble
from llmclean import strip_invisibles, normalize_typography, strip_markdown
import json

# --- JSON path ---

# Strip fences then parse JSON
data = json.loads(enforce_json(strip_fences(raw)))

# Reasoning model emitting fenced JSON after a <think> block
data = json.loads(enforce_json(strip_reasoning_trace(raw)))

# Full JSON pipeline — repetition, fences, and broken JSON together
data = json.loads(enforce_json(trim_repetition(strip_fences(raw))))

# --- Free-text path (e.g. preparing output for TTS) ---

# Pasted cloud output → clean ASCII prose
clean = normalize_typography(strip_invisibles(strip_markdown(raw)))

# Reasoning model → drop the trace, the filler, and the formatting
clean = strip_markdown(strip_preamble(strip_reasoning_trace(raw)))
```

Every function returns its input unchanged on failure or wrong type, so any order composes without an exception path.