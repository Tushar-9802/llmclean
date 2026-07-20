"""
_log.py — internal logging.

Every public function is contractually never-raise, which means 13 defensive
except blocks that would otherwise swallow bugs silently. They log instead.

Library convention: emit to a named logger with a NullHandler and let the
application decide. Nothing is printed unless the caller configures logging.

    logging.getLogger("llmclean").setLevel(logging.DEBUG)
    # or, for a quick look:
    llmclean.enable_debug_logging()
"""

import logging

logger = logging.getLogger("llmclean")
logger.addHandler(logging.NullHandler())


def log_failure(where, exc):
    """An exception the function was not expecting. Warn with a traceback.

    Swallows its own errors: these calls sit inside except blocks of never-raise
    functions, so a misconfigured handler must not become the thing that raises.
    """
    try:
        logger.warning("llmclean.%s returned its input unchanged after %s: %s",
                       where, type(exc).__name__, exc, exc_info=True)
    except Exception:
        pass


def log_fallback(where, detail):
    """An expected miss (no JSON present, nothing to strip). Debug only."""
    try:
        logger.debug("llmclean.%s fell back: %s", where, detail)
    except Exception:
        pass


def enable_debug_logging(level=logging.DEBUG, stream=None):
    """Send llmclean's internal logs to stderr. Opt-in convenience for debugging.

    Libraries should not configure logging on import, so this is explicit.
    """
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(level)
    return logger
