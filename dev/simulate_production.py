"""
simulate_production.py — generate a production-shaped corpus and run llmclean over it.

Production traffic is not just model output; it is model output AFTER transport.
Two stages:

  1. GENERATE — 5 local models x task matrix x decode conditions. Real output,
     including deliberately tiny caps so truncation actually happens.
  2. MUTATE — apply the damage that happens between the model and your parser:
     CRLF from Windows clients, BOM from gateways, mid-stream cutoff, HTML
     escaping, mojibake from a bad encoding round-trip, trailing whitespace.

Then every llmclean function runs over every (generation x mutation), capturing
escaped exceptions and internal WARNINGs (which now surface, since 0.4.0 logs).

    python dev/simulate_production.py generate    # slow, resumable
    python dev/simulate_production.py analyze     # fast, over the saved corpus
"""

import json
import logging
import random
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import llmclean as L  # noqa: E402

OLLAMA = "http://localhost:11434"
CORPUS = Path(__file__).resolve().parent / "production_corpus.jsonl"

LONG_CONTEXT = (
    "The quarterly report shows revenue of $4.2M, up 18% year over year. "
    "Headcount grew from 45 to 61. The Mumbai office opened in March. "
    "Churn was 3.1%, down from 4.8%. The board approved a Series B raise. "
) * 3

# Task matrix — spread across what people actually ask models to do.
TASKS = [
    ("json_flat", 'Extract name, age, city as JSON. Text: Ravi Kumar, 34, lives in Pune.'),
    ("json_nested", 'Return JSON with keys user{name,email}, active(bool), tags(array of 3). Invent plausible data.'),
    ("json_array", 'Extract every person as a JSON array of {name, role}. Text: Ana leads, Boris interns, Chen manages.'),
    ("json_from_context", f"From this report return JSON with revenue, growth_pct, headcount, churn_pct.\n\n{LONG_CONTEXT}"),
    ("json_empty_fields", 'Return JSON with keys title, subtitle, notes. Leave subtitle and notes empty strings.'),
    ("chat_answer", "What causes rain? Answer in three sentences."),
    ("summarize", f"Summarize in two sentences:\n\n{LONG_CONTEXT}"),
    ("markdown_doc", "Write a short guide to Python virtualenvs with headers, bullets, and a code block."),
    ("code_gen", "Write a Python function that parses a CSV file. Include a docstring and an example."),
    ("classify", "Classify the sentiment as positive/negative/neutral and explain: 'The delivery was late but support fixed it.'"),
    ("multilingual_hi", "हिंदी में दो वाक्य लिखिए कि वर्षा क्यों होती है।"),
    ("multilingual_zh", "用中文写两句话解释什么是机器学习。"),
    ("code_switched", "Reply in Hinglish: explain what an API is, mixing Hindi and English naturally."),
    ("echo_user_json", 'The user sent: {"cmd": "delete", "id": 7}. Explain what it does and repeat the JSON back.'),
    ("table_output", "Make a markdown table comparing REST and GraphQL on 3 dimensions."),
]

# Decode conditions, including a cap small enough to force truncation.
CONDITIONS = {
    "greedy":      {"temperature": 0, "num_predict": 250},
    "sampled":     {"temperature": 0.8, "top_p": 0.95, "num_predict": 250},
    "tiny_cap":    {"temperature": 0, "num_predict": 24},
    "no_penalty":  {"temperature": 0, "num_predict": 250,
                    "repeat_penalty": 1.0, "repeat_last_n": 0},
}


# --- transport mutations: what happens between the model and your parser ---

def m_identity(t):
    return t


def m_crlf(t):
    return t.replace("\n", "\r\n")


def m_bom(t):
    return "﻿" + t


def m_trailing_ws(t):
    return t + "   \n\n\t  "


def m_stream_cut(t):
    # Connection dropped mid-stream: cut at 70%, possibly mid-word.
    return t[: int(len(t) * 0.7)]


def m_html_escape(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def m_mojibake(t):
    # Classic UTF-8 bytes decoded as latin-1 somewhere in the chain.
    try:
        return t.encode("utf-8").decode("latin-1")
    except Exception:
        return t


def m_double_newline_join(t):
    # Streaming reassembly that duplicated a chunk boundary.
    parts = t.split("\n")
    return "\n\n".join(parts)


MUTATIONS = [
    ("identity", m_identity), ("crlf", m_crlf), ("bom", m_bom),
    ("trailing_ws", m_trailing_ws), ("stream_cut", m_stream_cut),
    ("html_escape", m_html_escape), ("mojibake", m_mojibake),
    ("double_nl", m_double_newline_join),
]

FUNCS = [
    ("load_json", L.load_json), ("clean_text", L.clean_text), ("check", L.check),
    ("enforce_json", L.enforce_json), ("strip_fences", L.strip_fences),
    ("strip_markdown", L.strip_markdown), ("strip_reasoning_trace", L.strip_reasoning_trace),
    ("strip_preamble", L.strip_preamble), ("strip_invisibles", L.strip_invisibles),
    ("normalize_typography", L.normalize_typography), ("trim_repetition", L.trim_repetition),
    ("degeneracy_score", L.degeneracy_score), ("collapse_word_runs", L.collapse_word_runs),
    ("collapse_intra_word_runs", L.collapse_intra_word_runs),
]


def generate(model, prompt, opts):
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": opts}).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.loads(r.read())
    # Reasoning models put everything in `thinking`; keep both.
    return d.get("response", ""), d.get("thinking", "") or ""


def list_models():
    with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=30) as r:
        return [m["name"] for m in json.loads(r.read())["models"]
                if "sakhi" not in m["name"].lower()]


def load_seen():
    if not CORPUS.exists():
        return set()
    seen = set()
    for line in CORPUS.open(encoding="utf-8"):
        try:
            r = json.loads(line)
            seen.add((r["model"], r["task"], r["condition"]))
        except Exception:
            continue
    return seen


def do_generate():
    models = list_models()
    seen = load_seen()
    todo = [(m, t, c) for m in models for t, _ in TASKS for c in CONDITIONS
            if (m, t, c) not in seen]
    print(f"{len(models)} models x {len(TASKS)} tasks x {len(CONDITIONS)} conditions")
    print(f"{len(todo)} generations remaining\n")
    prompts = dict(TASKS)
    done = 0
    with CORPUS.open("a", encoding="utf-8") as fout:
        for model, task, cond in todo:
            try:
                resp, think = generate(model, prompts[task], CONDITIONS[cond])
            except Exception as e:
                print(f"[ERR] {model}/{task}/{cond}: {e}")
                continue
            fout.write(json.dumps({"model": model, "task": task, "condition": cond,
                                   "response": resp, "thinking": think},
                                  ensure_ascii=False) + "\n")
            fout.flush()
            done += 1
            if done % 10 == 0:
                print(f"  {done}/{len(todo)}")
    print(f"\ndone: {done} new generations -> {CORPUS}")


def do_analyze():
    if not CORPUS.exists():
        print("no corpus yet; run: python dev/simulate_production.py generate")
        return

    warnings_seen = []

    class Cap(logging.Handler):
        def emit(self, rec):
            if rec.levelno >= logging.WARNING:
                warnings_seen.append(rec)

    L.logger.addHandler(Cap())
    L.logger.setLevel(logging.DEBUG)

    texts = []
    for line in CORPUS.open(encoding="utf-8"):
        r = json.loads(line)
        for field in ("response", "thinking"):
            if r.get(field):
                texts.append((r["model"], r["task"], r["condition"], field, r[field]))

    crashes = []
    calls = 0
    json_ok = json_tasks = 0
    truncated = degenerate = 0

    for model, task, cond, field, raw in texts:
        for mname, mut in MUTATIONS:
            try:
                text = mut(raw)
            except Exception as e:
                crashes.append((f"MUTATOR:{mname}", model, task, cond, repr(e)))
                continue
            for fname, fn in FUNCS:
                calls += 1
                try:
                    out = fn(text)
                except Exception as e:
                    crashes.append((fname, f"{model}/{task}/{cond}/{mname}",
                                    type(e).__name__, str(e)[:120], repr(text[:80])))
            if mname == "identity" and task.startswith("json"):
                json_tasks += 1
                json_ok += L.load_json(text) is not None
            if mname == "identity":
                rep = L.check(text)
                truncated += bool(rep["truncated"])
                degenerate += bool(rep["degenerate"])

    print(f"corpus:          {len(texts)} texts")
    print(f"mutations:       {len(MUTATIONS)}")
    print(f"functions:       {len(FUNCS)}")
    print(f"total calls:     {calls}")
    print(f"escaped crashes: {len(crashes)}")
    print(f"internal WARNs:  {len(warnings_seen)}")
    print()
    print(f"json tasks parsed to a dict: {json_ok}/{json_tasks}")
    print(f"flagged truncated:           {truncated}/{len(texts)}")
    print(f"flagged degenerate:          {degenerate}/{len(texts)}")

    for c in crashes[:20]:
        print("CRASH", c)
    for w in warnings_seen[:10]:
        print("WARN ", w.getMessage()[:160])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "analyze"
    (do_generate if cmd == "generate" else do_analyze)()
