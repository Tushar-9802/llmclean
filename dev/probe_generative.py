"""
probe_generative.py — baseline sweep of output "mess" across local models.

Where probe_models.py focused on JSON repair, this runs a VARIETY of generative
prompts (prose, lists, code, tables, multilingual, TTS-style) across every
pulled Ollama model and measures which classes of output mess actually appear.
Each mess-class maps to a candidate llmclean utility, so the printed matrix is a
direct, empirical justification (or refutation) for building each one:

    mess-class            -> utility it justifies
    fenced code block     -> strip_fences / extract_code
    markdown formatting    -> strip_markdown
    smart quotes           -> normalize_typography(quotes=)
    em/en dash             -> normalize_typography(dashes=)
    ellipsis char (U+2026) -> normalize_typography(ellipsis=)
    nbsp / exotic spaces   -> normalize_typography(spaces=)
    ligatures              -> normalize_typography(ligatures=)
    zero-width / invisible -> strip_invisibles
    fullwidth punctuation  -> normalize_typography(fullwidth=)  [opt-in]
    <think> tag inline     -> strip_reasoning_trace
    py-literal / single-q  -> enforce_json (existing)

Results append (flushed) to dev/probe_generative.jsonl — resumable, crash-safe.

Usage:
    python dev/probe_generative.py                 # all models, all prompts
    python dev/probe_generative.py llama3.1:8b
"""

import json
import sys
import urllib.request
from pathlib import Path

OLLAMA = "http://localhost:11434"
OUT_PATH = Path(__file__).resolve().parent / "probe_generative.jsonl"

# Prompts chosen so DIFFERENT output mess surfaces. We don't care about answer
# quality — only the formatting wrapper each model habitually emits.
PROMPTS = [
    {"id": "essay",
     "prompt": "Write a 4-sentence paragraph about the history of the typewriter. "
               "Use natural punctuation."},
    {"id": "explain_list",
     "prompt": "Explain how photosynthesis works, using headers and bullet points."},
    {"id": "code",
     "prompt": "Write a Python function that reverses a string. Include a short explanation."},
    {"id": "table",
     "prompt": "Make a markdown table comparing TCP and UDP across 3 properties."},
    {"id": "tts_simple",
     "prompt": "In plain spoken English with no formatting, explain what a black hole is "
               "in two sentences."},
    {"id": "multilingual",
     "prompt": "用中文写两句话介绍长城，并用合适的标点符号。"},
    {"id": "quote_heavy",
     "prompt": "Write a sentence that quotes someone saying \"hello\" and uses a dash "
               "for emphasis, plus an ellipsis to trail off."},
    {"id": "json_extract",
     "prompt": "Extract name, role and active(boolean) as JSON. "
               "Text: Priya is the lead engineer and is currently active."},
]


def generate(model: str, prompt: str) -> dict:
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "options": {"temperature": 0.2},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA}/api/generate", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())


def list_models() -> list:
    with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=30) as resp:
        names = [m["name"] for m in json.loads(resp.read())["models"]]
    # skip the custom sakhi fine-tunes for a clean base-model baseline
    return [n for n in names if "sakhi" not in n.lower()]


# --- mess detectors: each returns True if that class is present in raw text ---
SMART_QUOTES = "“”‘’„‚‹›«»"
DASHES = "—–―−"
EXOTIC_SPACES = "           　"
LIGATURES = "ﬀﬁﬂﬃﬄﬅﬆ"
INVISIBLES = "​‌⁠﻿­᠎‎‏‪‫‬‭‮"
FULLWIDTH_PUNCT = "，：；！？（）「」、。"


def has_any(text: str, chars: str) -> bool:
    return any(c in text for c in chars)


def has_markdown(text: str) -> bool:
    import re
    return bool(re.search(r"(^|\n)#{1,6}\s", text) or       # headers
                re.search(r"\*\*[^*\n]+\*\*", text) or       # bold
                re.search(r"(^|\n)\s*[-*+]\s+\S", text) or   # bullets
                re.search(r"\[[^\]]+\]\([^)]+\)", text))     # links


def has_zwj_in_emoji(text: str) -> bool:
    # ZWJ between two non-ASCII chars = legitimate emoji sequence (must survive).
    import re
    return bool(re.search(r"[^\x00-\x7f]‍[^\x00-\x7f]", text))


def diagnose(raw: str) -> dict:
    return {
        "fence":        "```" in raw,
        "markdown":     has_markdown(raw),
        "smart_quotes": has_any(raw, SMART_QUOTES),
        "dashes":       has_any(raw, DASHES),
        "ellipsis":     "…" in raw,
        "exotic_space": has_any(raw, EXOTIC_SPACES),
        "ligatures":    has_any(raw, LIGATURES),
        "invisibles":   has_any(raw, INVISIBLES),
        "emoji_zwj":    has_zwj_in_emoji(raw),
        "fullwidth":    has_any(raw, FULLWIDTH_PUNCT),
        "think_tag":    "<think" in raw.lower() or "</think" in raw.lower(),
    }


def load_seen(path: Path) -> set:
    if not path.exists():
        return set()
    seen = set()
    for line in path.open(encoding="utf-8"):
        try:
            r = json.loads(line)
            seen.add((r["model"], r["prompt_id"]))
        except Exception:
            continue
    return seen


def main():
    wanted = sys.argv[1:] or list_models()
    seen = load_seen(OUT_PATH)
    # matrix[mess_class] = set of "model/prompt" where it appeared
    matrix = {}

    with OUT_PATH.open("a", encoding="utf-8") as fout:
        for model in wanted:
            for p in PROMPTS:
                if (model, p["id"]) in seen:
                    continue
                try:
                    r = generate(model, p["prompt"])
                except Exception as e:
                    print(f"[ERR] {model} / {p['id']}: {e}")
                    continue
                raw = r.get("response", "")
                # Ollama splits reasoning out; capture it so we can see the
                # real trace even though it won't be inline in `response`.
                thinking = r.get("thinking") or ""
                diag = diagnose(raw)
                # also check whether the SPLIT-OUT thinking field exists
                diag_think_field = bool(thinking)
                row = {
                    "model": model, "prompt_id": p["id"],
                    "diag": diag, "thinking_field": diag_think_field,
                    "raw": raw, "thinking": thinking,
                }
                fout.write(json.dumps(row, ensure_ascii=False) + "\n")
                fout.flush()
                present = [k for k, v in diag.items() if v]
                for k in present:
                    matrix.setdefault(k, set()).add(f"{model.split(':')[0]}/{p['id']}")
                tf = " +think_field" if diag_think_field else ""
                print(f"[{model.split(':')[0]:12s} {p['id']:13s}] "
                      f"{' '.join(present)}{tf}")

    print("\n=== mess-class coverage matrix (where each class appeared) ===")
    for cls in ["fence", "markdown", "smart_quotes", "dashes", "ellipsis",
                "exotic_space", "ligatures", "invisibles", "emoji_zwj",
                "fullwidth", "think_tag"]:
        hits = matrix.get(cls, set())
        mark = "OK " if hits else "-- "
        print(f"{mark}{cls:13s} {len(hits):2d}  {', '.join(sorted(hits)) or '(none seen)'}")
    print(f"\nFull rows: {OUT_PATH}")


if __name__ == "__main__":
    main()
