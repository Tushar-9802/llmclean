# Changelog

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
