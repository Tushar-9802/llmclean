"""
probe_degeneration.py — does local inference actually degenerate, and with what signature?

The degeneration study measured HF's no_repeat_ngram_size, a HARD trigram ban,
which truncates unbounded loops into exactly-3 runs. Ollama/llama.cpp use
repeat_penalty (a SOFT logit penalty) + repeat_last_n instead. Different
mechanism, so possibly a different signature. This measures it.

Conditions per model:
  masked   — Ollama defaults (repeat_penalty 1.1, repeat_last_n 64)
  unmasked — penalties off (repeat_penalty 1.0, repeat_last_n 0)

Greedy decode (temperature 0) throughout: maximization-based decoding is what
provokes loops in the first place.

Appends to dev/probe_degeneration.jsonl (resumable).
"""

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from llmclean import degeneracy_score  # noqa: E402

OLLAMA = "http://localhost:11434"
OUT_PATH = Path(__file__).resolve().parent / "probe_degeneration.jsonl"
NUM_PREDICT = 400

# Prompts that invite looping: open-ended, unbounded, or repetitive-structure.
PROMPTS = [
    {"id": "unbounded_list",
     "prompt": "List synonyms for the word 'good'. Keep going, do not stop."},
    {"id": "open_continue",
     "prompt": "Continue this text forever: The system processes data and"},
    {"id": "long_technical",
     "prompt": "Explain backpropagation in a neural network in exhaustive detail."},
    {"id": "recursive",
     "prompt": "Describe a loop that describes itself describing a loop."},
    {"id": "count_forever",
     "prompt": "Count upward in words, starting at one, and never stop."},
]

CONDITIONS = {
    "masked":   {"repeat_penalty": 1.1, "repeat_last_n": 64},
    "unmasked": {"repeat_penalty": 1.0, "repeat_last_n": 0},
}


def generate(model, prompt, opts):
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "options": {"temperature": 0, "num_predict": NUM_PREDICT, **opts},
    }).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read()).get("response", "")


def list_models():
    with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=30) as r:
        names = [m["name"] for m in json.loads(r.read())["models"]]
    return [n for n in names if "sakhi" not in n.lower()]


def max_word_run(text):
    """Longest run of identical adjacent words — tests the exactly-3 hypothesis."""
    words = [w.lower() for w in text.split()]
    best = run = 1
    for i in range(1, len(words)):
        run = run + 1 if words[i] == words[i - 1] else 1
        best = max(best, run)
    return best if words else 0


def load_seen(path):
    if not path.exists():
        return set()
    seen = set()
    for line in path.open(encoding="utf-8"):
        try:
            r = json.loads(line)
            seen.add((r["model"], r["prompt_id"], r["condition"]))
        except Exception:
            continue
    return seen


def main():
    models = sys.argv[1:] or list_models()
    seen = load_seen(OUT_PATH)
    stats = {}

    with OUT_PATH.open("a", encoding="utf-8") as fout:
        for model in models:
            for cond, opts in CONDITIONS.items():
                for p in PROMPTS:
                    key = (model, p["id"], cond)
                    if key in seen:
                        continue
                    try:
                        raw = generate(model, p["prompt"], opts)
                    except Exception as e:
                        print(f"[ERR] {model}/{p['id']}/{cond}: {e}")
                        continue
                    score = degeneracy_score(raw, cap_tokens=NUM_PREDICT)
                    row = {
                        "model": model, "prompt_id": p["id"], "condition": cond,
                        "max_word_run": max_word_run(raw),
                        "score": score, "raw": raw,
                    }
                    fout.write(json.dumps(row, ensure_ascii=False) + "\n")
                    fout.flush()

                    s = stats.setdefault((model.split(":")[0], cond),
                                         {"n": 0, "deg": 0, "maxrun": 0, "rules": {}})
                    s["n"] += 1
                    s["deg"] += bool(score["degenerate"])
                    s["maxrun"] = max(s["maxrun"], row["max_word_run"])
                    for r in score["rules_fired"]:
                        s["rules"][r] = s["rules"].get(r, 0) + 1
                    flag = "DEGEN" if score["degenerate"] else "  ok "
                    print(f"[{flag}] {model.split(':')[0]:12s} {cond:8s} "
                          f"{p['id']:15s} run={row['max_word_run']:<3d} "
                          f"{','.join(score['rules_fired'])}")

    print("\n=== summary: degenerate / total, longest adjacent run ===")
    for (model, cond), s in sorted(stats.items()):
        print(f"{model:12s} {cond:8s} {s['deg']}/{s['n']} degenerate  "
              f"longest_run={s['maxrun']}  {s['rules']}")
    print(f"\nRows: {OUT_PATH}")


if __name__ == "__main__":
    main()
