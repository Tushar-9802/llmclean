# llmclean — Usage Guide

Full examples for every function with real inputs and outputs you can paste and run.

```bash
cd llmclean
python3
>>> from llmclean import strip_fences, enforce_json, trim_repetition
```

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

**Strategies in order:** parse as-is → strip fences → extract JSON substring from prose → fix trailing commas → fix Python literals → fix unquoted keys → close open brackets → all combined.

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

## Combining functions

The three functions are independent and chain naturally:

```python
from llmclean import strip_fences, enforce_json, trim_repetition
import json

# Strip fences then parse JSON
data = json.loads(enforce_json(strip_fences(raw)))

# Full pipeline — handles repetition, fences, and broken JSON together
data = json.loads(enforce_json(trim_repetition(strip_fences(raw))))

# Just clean up text output (no JSON involved)
clean = trim_repetition(strip_fences(raw))
```