# llmclean

Small Python library for cleaning the noise out of raw LLM output. Strips markdown fences, repairs malformed JSON, trims runaway repetitions, removes reasoning traces and conversational filler, flattens markdown to prose, normalizes invisible/typographic Unicode, and reports model degeneration instead of silently hiding it. Zero runtime dependencies — pure standard library.

I built this because my other projects ([Sakhi](https://github.com/Tushar-9802/Sakhi), [Resume-parser](https://github.com/Tushar-9802/Resume-parser)) kept reinventing the same five or six regex passes against the same recurring failure modes. The [changelog](CHANGELOG.md) documents what production traffic — and, for 0.3.0, a five-model local sweep — taught me to fix here.

## Install

```bash
pip install llmclean
```

## Parse JSON out of messy LLM output

```python
import llmclean

llmclean.load_json('Sure! Here you go:\n```json\n{"ok": True, "n": [1,2,3,]}\n```')
# → {'ok': True, 'n': [1, 2, 3]}          a real dict, not a string
```

That one call strips the reasoning trace, unwraps the fence, discards the prose around it, fixes the Python `True` and the trailing comma, and parses. Returns `None` (or your `default=`) if there's genuinely no JSON in there. It never raises.

## Three front doors

Nearly everyone arrives with one of three goals:

```python
data   = llmclean.load_json(raw)    # I asked for JSON  → dict/list, or None
text   = llmclean.clean_text(raw)   # I asked for prose → clean plain text
report = llmclean.check(raw)        # is this output broken?
```

```python
# Strip <think> blocks, "Sure! Here's...", markdown, and smart quotes in one pass
llmclean.clean_text('<think>hmm</think>Sure! Here is the answer:\n\n# Title\n\n- **bold** point')
# → 'Title\n\nbold point'

# Detect degeneration instead of silently hiding it
llmclean.check("We tune the parameter parameter parameter values today.")
# → {'degenerate': True,
#    'rules_fired': ['top_token_frac', 'adjacent_dup_rate'], ...}
```

## Going deeper

The front doors are composition over a dozen single-purpose functions. Use them directly when you want to control the pipeline:

| Function | Removes / does |
|---|---|
| `strip_fences` | ` ``` ` and `~~~` wrappers, incl. CRLF and unclosed fences |
| `enforce_json` | repairs malformed JSON (returns a string) |
| `trim_repetition` | runaway repeated sentences at the tail |
| `strip_reasoning_trace` | `<think>…</think>` blocks, incl. DeepSeek's lone `</think>` |
| `strip_preamble` | "Sure! Here's…" / "Hope that helps!" |
| `strip_markdown` | headers, bold, bullets, links → plain prose |
| `strip_invisibles` | zero-width and control characters |
| `normalize_typography` | smart quotes, em dashes, ellipsis → ASCII |
| `degeneracy_score` | full degeneration report (5 rules) |
| `collapse_word_runs` | `"parameter parameter parameter"` → `"parameter"` |
| `collapse_intra_word_runs` | `"thresholdinginginging"` → `"thresholding"` |

Every one of them returns its input unchanged on failure or wrong type, so any order composes without an exception path. Full examples in [USAGE.md](USAGE.md).

Scope is measured, not assumed: the text functions come from a five-model local sweep (llama3.1 / gemma4 / qwen2.5 / deepseek-r1 / mistral). The [changelog](CHANGELOG.md) records what reproduced locally (markdown, fences, fullwidth-in-prose) versus what is a frontier-cloud-model trait tested with synthetic fixtures (smart quotes, em dashes, zero-width characters).

## Common tasks

| If you're trying to… | Use |
|---|---|
| parse JSON from an LLM response in Python | `llmclean.load_json(raw)` |
| fix invalid JSON returned by GPT / Claude / Llama | `llmclean.load_json(raw)` |
| remove `<think>` tags from DeepSeek-R1 output | `strip_reasoning_trace(raw)` |
| strip markdown from an LLM response for TTS | `strip_markdown(raw)` |
| remove "Sure! Here's" preamble from a model answer | `strip_preamble(raw)` |
| remove em dashes / smart quotes from AI text | `normalize_typography(raw)` |
| remove zero-width / invisible characters from AI text | `strip_invisibles(raw)` |
| detect when a model is repeating itself or degenerating | `llmclean.check(raw)` |

## Debugging

Every public function is never-raise: on failure it returns its input unchanged. That guarantee used to make internal bugs invisible. It no longer does — each fallback logs to a standard named logger, silent by default:

```python
import llmclean
llmclean.enable_debug_logging()      # or configure logging.getLogger("llmclean")

llmclean.strip_markdown(weird_input)
# WARNING llmclean: llmclean.strip_markdown returned its input unchanged
#   after AttributeError: ...
# Traceback (most recent call last): ...
```

Unexpected failures log at `WARNING` with a full traceback; expected misses (no JSON present) log at `DEBUG`. Nothing is emitted unless your application configures logging, per standard library practice. A broken log handler still can't make a call raise.

## What it doesn't do (and the thing to use instead)

- Validate JSON against a schema — use `jsonschema` or `pydantic`
- Re-prompt the model to fix its output — use `instructor`
- Constrain the model at generation time so it can't produce broken output — use `outlines`

These are different problems with different tools. llmclean handles the post-hoc cleanup pass; compose it with the above if you need more.

## Design choices

Three constraints kept while iterating:

The library should never raise. Every public function returns the original input on failure, so it composes safely in pipelines that can't afford an exception path.

Stay zero-dep. The standard library is sufficient for what this needs to do, and pulling in a dependency would force every downstream user to deal with version conflicts they didn't sign up for.

Be predictable. Same input always produces the same output. No external state, no model calls, no fuzzy heuristics that change behaviour silently across versions.

## Known limitations

Some inputs land llmclean in known false-positive territory. Two worth flagging:

`strip_fences` will remove a single language name if it's the only content inside a fence — so if your model literally emits `` ```\njson\n``` `` as a one-word answer, that content disappears. The aggressive language-tag cleanup catches stray tags from real-world fence variants, and the trade-off is documented in the test `test_lone_language_word_as_content_gets_stripped`.

`enforce_json`'s double-quote collapse only handles the symmetric form `""text""`. The asymmetric variants Sakhi's pipeline also handles (`: ""x` and `x""`) corrupt legitimate empty-string values, so they're deliberately omitted here.

## Tests

```bash
pip install "llmclean[dev]"
pytest -v
```

194 tests across the modules at 0.4.0. Includes characterization tests for known trade-offs (empty-string preservation, lone-language-tag strip) and real-model-output fixtures (deepseek-r1 reasoning trace, gemma4 markdown) so future changes can't silently regress them.

## License

MIT.
