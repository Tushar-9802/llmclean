"""
probe_models.py — empirical failure-mode collector for llmclean.

Runs a battery of extraction prompts across whatever local Ollama models are
pulled, captures the RAW output, then classifies what cleanup (if any) the
current llmclean pipeline can apply:

    clean-direct   json.loads(raw) already works            -> no cleanup needed
    cleaned        enforce_json(raw) parses, raw did not     -> llmclean earns its keep
    still-broken   enforce_json(raw) still not valid JSON    -> NEW strategy candidate

Every result row is appended (JSONL, flushed per row) to dev/probe_results.jsonl
so a crash mid-run loses nothing and re-runs are resumable. The still-broken and
"raw needed fullwidth/preamble fixing" piles are the input to deciding which
utilities are worth building next.

Usage:
    python dev/probe_models.py                 # all pulled models, all prompts
    python dev/probe_models.py qwen2.5:7b-instruct
"""

import json
import sys
import urllib.request
from pathlib import Path

# Import the library under test from the parent dir.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from llmclean import enforce_json  # noqa: E402

OLLAMA = "http://localhost:11434"
OUT_PATH = Path(__file__).resolve().parent / "probe_results.jsonl"

# Prompts chosen to stress distinct failure modes, not to get clean answers.
PROMPTS = [
    {
        "id": "plain",
        "mode": "baseline extraction",
        "prompt": "Extract name and age as JSON. Text: Ravi is 28 years old.",
    },
    {
        "id": "reason_first",
        "mode": "preamble / reasoning leak",
        "prompt": (
            "Think step by step about the text, explain your reasoning, "
            "and THEN give the JSON. Text: The order shipped on Tuesday for $42."
        ),
    },
    {
        "id": "mixed_cjk",
        "mode": "fullwidth punctuation (CJK activation)",
        "prompt": (
            "下面的文本里提取人名和城市，输出 JSON。"
            "Text: 王伟 lives in 上海. Keys must be name and city."
        ),
    },
    {
        "id": "nested_schema",
        "mode": "trailing comma / single quote / py-literal",
        "prompt": (
            "Return a JSON object with keys: user (string), active (boolean), "
            "tags (array of 3 strings), meta (object with one key 'note'). "
            "Use the value true for active. Fill with plausible data."
        ),
    },
    {
        "id": "list_of_objs",
        "mode": "array-of-objects, often over-explained",
        "prompt": (
            "Extract all people as a JSON array of objects with name and role. "
            "Text: Ana is the lead, Boris is the intern, Chen is the manager."
        ),
    },
]


def generate(model: str, prompt: str) -> str:
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA}/api/generate", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())["response"]


def list_models() -> list:
    with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=30) as resp:
        return [m["name"] for m in json.loads(resp.read())["models"]]


def parses(text: str) -> bool:
    try:
        json.loads(text.strip())
        return True
    except Exception:
        return False


def classify(raw: str) -> str:
    if parses(raw):
        return "clean-direct"
    if parses(enforce_json(raw)):
        return "cleaned"
    return "still-broken"


# Characters worth flagging in the raw, to spot utility gaps quickly.
FULLWIDTH = "，：；！？（）「」、。"


def diagnostics(raw: str) -> dict:
    return {
        "has_fullwidth": any(c in raw for c in FULLWIDTH),
        "has_think_tag": "<think" in raw.lower() or "<thinking" in raw.lower(),
        "has_fence": "```" in raw,
        "len": len(raw),
        # crude preamble signal: text before the first { or [
        "preamble_chars": min((raw.find("{") % (len(raw) + 1)),
                              (raw.find("[") if raw.find("[") != -1 else len(raw))),
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
    summary = {}

    with OUT_PATH.open("a", encoding="utf-8") as fout:
        for model in wanted:
            for p in PROMPTS:
                key = (model, p["id"])
                if key in seen:
                    continue
                try:
                    raw = generate(model, p["prompt"])
                except Exception as e:
                    print(f"[ERR ] {model} / {p['id']}: {e}")
                    continue
                verdict = classify(raw)
                row = {
                    "model": model,
                    "prompt_id": p["id"],
                    "mode": p["mode"],
                    "verdict": verdict,
                    "diag": diagnostics(raw),
                    "raw": raw,
                }
                fout.write(json.dumps(row, ensure_ascii=False) + "\n")
                fout.flush()
                summary.setdefault(model, {}).setdefault(verdict, 0)
                summary[model][verdict] += 1
                flags = [k for k, v in row["diag"].items()
                         if v is True]
                print(f"[{verdict:12s}] {model:32s} {p['id']:14s} "
                      f"{' '.join(flags)}")

    print("\n=== summary ===")
    for model, counts in summary.items():
        print(f"{model}: {counts}")
    print(f"\nFull rows: {OUT_PATH}")


if __name__ == "__main__":
    main()
