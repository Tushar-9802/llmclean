# llmclean

**A zero-dependency Python library for cleaning and normalizing raw LLM output.**

LLMs are inconsistent: they wrap JSON in markdown fences, add prose around code, repeat themselves, and produce subtly broken JSON. `llmclean` handles all of that with three focused utilities.

---

## Install

```bash
pip install llmclean
```

---

## Quick start

```python
from llmclean import strip_fences, enforce_json, trim_repetition

# Remove ```json ... ``` wrappers
strip_fences('```json\n{"name": "Alice"}\n```')
# → '{"name": "Alice"}'

# Extract valid JSON from messy output
enforce_json('Here you go: {"ok": True, "items": [1,2,3,]}')
# → '{\n  "ok": true,\n  "items": [1, 2, 3]\n}'

# Remove repeated sentences/paragraphs at the end
trim_repetition("The answer is 42. This is final. This is final.")
# → 'The answer is 42. This is final.'
```

For full examples and edge cases see **[USAGE.md](USAGE.md)**.

---

## Functions

| Function | What it fixes |
|---|---|
| `strip_fences(text)` | Removes ` ```lang ` / ` ``` ` / `~~~` code fences |
| `enforce_json(text)` | Extracts valid JSON from fences, prose, trailing commas, Python literals, unquoted keys, unclosed brackets |
| `trim_repetition(text)` | Removes repeated sentences, near-duplicates, and repeated paragraphs from the tail |

---

## Design principles

- **Zero dependencies** — pure Python standard library
- **Never throws** — every function returns the original input if cleaning fails
- **Non-destructive** — unchanged input when nothing needs cleaning
- **Composable** — chain freely

```python
# Full pipeline
data = enforce_json(trim_repetition(strip_fences(raw_output)))
```

---

## Running tests

```bash
# With pytest
pip install "llmclean[dev]"
pytest -v

# Without pytest
python run_tests.py
```

---

## License

MIT