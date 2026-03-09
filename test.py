from llmclean import strip_fences, enforce_json, trim_repetition
import json
text = "```json\n{\"name\": \"John\", \"age\": 30}\n```"
print(strip_fences(text))
print(enforce_json(text))
print(trim_repetition(text))

# ── enforce_json: Python literals ──────────────────────────────────────────
print(enforce_json('{"active": True, "deleted": False, "alias": None}'))
# expect: true / false / null

print(enforce_json("{'name': 'Alice', 'age': 30}"))
# expect: valid JSON with double quotes

# ── enforce_json: broken + combined ────────────────────────────────────────
print(enforce_json('{"a": 1, "b": 2,}'))
# expect: no trailing comma

print(enforce_json('```json\n{"ok": True, "items": [1,2,3,],}\n```'))
# expect: true, clean array, no trailing comma

print(enforce_json('{name: "Alice", age: 30}'))
# expect: quoted keys

print(enforce_json('{"a": [1, 2'))
# expect: closed brackets

print(enforce_json('Here is your result: {"x": 1, "y": 2} Hope that helps!'))
# expect: just the JSON, no prose

# ── enforce_json: should fail gracefully ───────────────────────────────────
result = enforce_json("this is not json at all")
print(result == "this is not json at all")
# expect: True — original returned unchanged

# ── trim_repetition: the fuzzy cases ───────────────────────────────────────
print(trim_repetition(
    "The answer is 42. "
    "This is the final answer. "
    "This is the final answer. "
    "This is the final answer."
))
# expect: one copy of 'This is the final answer.'

print(trim_repetition(
    "Important intro content that must survive. "
    "This sentence repeats. "
    "This sentence repeats."
))
# expect: intro preserved, one copy of repeated sentence

print(trim_repetition(
    "Opening paragraph.\n\n"
    "This paragraph repeats and has enough length.\n\n"
    "This paragraph repeats and has enough length."
))
# expect: intro + one copy of paragraph

# ── none/wrong type — nothing should crash ─────────────────────────────────
print(strip_fences(None))    # → None
print(enforce_json(None))    # → None
print(trim_repetition(None)) # → None
print(strip_fences(42))      # → 42
print(enforce_json(42))      # → 42
print(trim_repetition(42))   # → 42

# ── final sanity: every enforce_json output is valid JSON ──────────────────
cases = [
    '```json\n{"x": 1}\n```',
    '{"ok": True}',
    "{'a': 'b'}",
    '{"a": 1,}',
    '[1, 2, 3,]',
    '{name: "Alice"}',
    '{"a": [1, 2',
    'Some prose {"buried": true} in here',
]
for c in cases:
    result = enforce_json(c)
    try:
        json.loads(result)
        print(f"OK: {c[:40]}")
    except:
        print(f"FAILED: {c[:40]}")