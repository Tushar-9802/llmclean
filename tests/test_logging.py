"""Tests for internal logging.

The library is contractually never-raise, which means defensive except blocks
that would otherwise swallow bugs. These pin the behaviour: silent by default,
visible on request, and never at the cost of raising.
"""

import logging


import llmclean
import llmclean.markdown as md_mod


def test_silent_by_default(caplog):
    # A library must not emit anything unless the application configures logging.
    assert isinstance(llmclean.logger.handlers[0], logging.NullHandler)


def test_internal_failure_is_logged_with_traceback(caplog, monkeypatch):
    monkeypatch.setattr(md_mod, "_HEADER_RE", None)   # simulate an internal bug
    with caplog.at_level(logging.WARNING, logger="llmclean"):
        out = llmclean.strip_markdown("# Title")
    assert out == "# Title"                            # never-raise contract holds
    assert any("strip_markdown" in r.message for r in caplog.records)
    assert any(r.exc_info for r in caplog.records)     # traceback attached


def test_expected_miss_logs_at_debug_not_warning(caplog):
    # No JSON present is a normal outcome, not a bug — must not warn.
    with caplog.at_level(logging.DEBUG, logger="llmclean"):
        assert llmclean.load_json("no json here") is None
    assert any(r.levelno == logging.DEBUG for r in caplog.records)
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)


def test_enable_debug_logging_attaches_handler():
    before = len(llmclean.logger.handlers)
    try:
        llmclean.enable_debug_logging()
        assert len(llmclean.logger.handlers) > before
        assert llmclean.logger.level == logging.DEBUG
    finally:
        llmclean.logger.handlers = llmclean.logger.handlers[:before]
        llmclean.logger.setLevel(logging.NOTSET)


def test_broken_handler_does_not_break_the_call(monkeypatch):
    # A misconfigured handler must not become the thing that raises.
    class ExplodingHandler(logging.Handler):
        def emit(self, record):
            raise RuntimeError("handler exploded")

    handler = ExplodingHandler()
    llmclean.logger.addHandler(handler)
    llmclean.logger.setLevel(logging.DEBUG)
    monkeypatch.setattr(md_mod, "_HEADER_RE", None)
    try:
        assert llmclean.strip_markdown("# Title") == "# Title"   # still returns
    finally:
        llmclean.logger.removeHandler(handler)
        llmclean.logger.setLevel(logging.NOTSET)
