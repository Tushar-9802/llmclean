# Contributing to llmclean

Thanks for your interest in contributing. This is a small, focused library — contributions that fix real LLM output patterns, improve robustness, or catch edge cases are very welcome.

---

## Setup

You need Python 3.9 or newer. No other system dependencies.

```bash
# 1. Clone the repo
git clone https://github.com/your-username/llmclean.git
cd llmclean

# 2. Install the package in editable mode, including dev dependencies
pip install -e ".[dev]"
```

That installs `llmclean` itself (editable, so your changes take effect immediately) plus `pytest`.

---

## Running the tests

```bash
# Run the full suite
pytest

# Verbose output (recommended — shows each test name)
pytest -v

# Run a single file
pytest tests/test_json.py -v

# Run a single test by name
pytest tests/test_json.py::test_python_true_false_none -v
```

**No network / no pytest installed?** A zero-dependency runner is included:

```bash
python run_tests.py
```

This works with nothing but a standard Python install and is how tests are run in this repo's offline build environment.

---

## Project structure

```
llmclean/
├── llmclean/              # importable package
│   ├── __init__.py        # public API: strip_fences, enforce_json, trim_repetition
│   ├── fences.py          # strip_fences()
│   ├── json_utils.py      # enforce_json()
│   └── repetition.py      # trim_repetition()
├── tests/
│   ├── test_fences.py
│   ├── test_json.py
│   └── test_repetition.py
├── run_tests.py           # zero-dependency test runner
├── pyproject.toml
├── README.md
└── CONTRIBUTING.md        # this file
```

---

## Maintenance status

This library is provided as-is and is not actively maintained. Issues and pull requests may not be reviewed or responded to. If it doesn't do what you need, fork it — the codebase is small and intentionally straightforward to modify.