# llmclean

Small Python library for cleaning the noise out of raw LLM output. Strips markdown fences, repairs malformed JSON, trims runaway repetitions, removes reasoning traces and conversational filler, flattens markdown to prose, and normalizes invisible/typographic Unicode. Zero runtime dependencies — pure standard library.

I built this because my other projects ([Sakhi](https://github.com/Tushar-9802/Sakhi), [Resume-parser](https://github.com/Tushar-9802/Resume-parser)) kept reinventing the same five or six regex passes against the same recurring failure modes. The [changelog](CHANGELOG.md) documents what production traffic — and, for 0.3.0, a five-model local sweep — taught me to fix here.

## Install

```bash
pip install llmclean
```

## What it does

```python
from llmclean import strip_fences, enforce_json, trim_repetition
from llmclean import strip_reasoning_trace, strip_preamble
from llmclean import strip_invisibles, normalize_typography, strip_markdown

# ```lang ... ``` wrappers, including tilde fences and CRLF line endings
strip_fences('```json\n{"name": "Alice"}\n```')
# → '{"name": "Alice"}'

# JSON buried in prose, with trailing comma + Python literals
enforce_json('Here you go: {"ok": True, "items": [1,2,3,]}')
# → '{\n  "ok": true,\n  "items": [1, 2, 3]\n}'

# Model looped on the same sentence
trim_repetition("The answer is 42. This is final. This is final.")
# → 'The answer is 42. This is final.'

# Reasoning-model <think> block (llama.cpp / vLLM / transformers inline it)
strip_reasoning_trace("<think>let me work it out</think>\nParis.")
# → 'Paris.'

# Conversational filler on the front/back
strip_preamble("Sure! Here is the answer: 42")
# → '42'

# Zero-width / control characters that silently break search & regex
strip_invisibles("hel​lo﻿")          # → 'hello'

# Smart quotes / em dash / ellipsis from pasted cloud output → ASCII
normalize_typography('“It’s fine”—really…')      # → '"It\'s fine"-really...'

# Flatten markdown to prose (TTS, voice bots, plain fields)
strip_markdown("# Title\n\n- **bold** point with `code`")
# → 'Title\n\nbold point with code'
```

`enforce_json` runs a pipeline of strategies in order and stops at the first one that produces parseable JSON. Strategies cover: existing valid JSON, fences, prose around the JSON, BOM at position 0, doubled-quote overruns like `""value""`, trailing commas, Python `True`/`False`/`None`, single-quoted strings, unquoted keys, and unclosed brackets. Full set in [USAGE.md](USAGE.md).

The text functions are scoped from a five-model local sweep (llama3.1 / gemma4 / qwen2.5 / deepseek-r1 / mistral) plus where the ecosystem already re-implements these by hand — see the [0.3.0 changelog](CHANGELOG.md) for what reproduced locally (markdown, fences, fullwidth-in-prose) versus what is a frontier-cloud-model trait served via synthetic fixtures (smart quotes, em dashes, zero-width characters).

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

138 tests across the modules at 0.3.0. Includes characterization tests for known trade-offs (empty-string preservation, lone-language-tag strip) and real-model-output fixtures (deepseek-r1 reasoning trace, gemma4 markdown) so future changes can't silently regress them.

## License

MIT.
