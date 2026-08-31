"""Optional staging helper for sanitized Shopee diagnostics.

Diagnostics are disabled unless SHOPEE_DIAGNOSTICS=1. When enabled, capture is
request-local via ContextVar so simultaneous users cannot receive each other's
Shopee diagnostic lines. asyncio.to_thread copies the current context, so the
capture follows the download worker without relying on a process-global buffer.
"""

import builtins
import contextvars
import os
import re

_ENABLED = os.getenv("SHOPEE_DIAGNOSTICS", "0").strip().lower() in {"1", "true", "yes", "on"}
_CURRENT_LINES = contextvars.ContextVar("jetbot_shopee_diag_lines", default=None)
_ORIGINAL_PRINT = builtins.print


def _sanitize(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"https?://[^\s\"']+", "<URL>", text)
    text = re.sub(r"[A-Za-z0-9_\-]{80,}", "<LONG_TOKEN>", text)
    return text[:700]


def begin_shopee_diagnostics():
    """Start an isolated capture for the current request/context."""
    if not _ENABLED:
        return None
    return _CURRENT_LINES.set([])


def end_shopee_diagnostics(token) -> str:
    """Return the current request's diagnostics and restore the prior context."""
    if not _ENABLED or token is None:
        return ""
    lines = _CURRENT_LINES.get() or []
    try:
        _CURRENT_LINES.reset(token)
    except Exception:
        _CURRENT_LINES.set(None)
    return ("\n".join(lines) + "\n") if lines else ""


def _capture_print(*args, **kwargs):
    try:
        rendered = " ".join(str(arg) for arg in args)
        lines = _CURRENT_LINES.get()
        if lines is not None and rendered.startswith("[JetBot Shopee]"):
            if len(lines) < 240:
                lines.append(_sanitize(rendered))
    except Exception:
        pass
    return _ORIGINAL_PRINT(*args, **kwargs)


if _ENABLED and not getattr(builtins, "_jetbot_shopee_diag_capture", False):
    builtins.print = _capture_print
    builtins._jetbot_shopee_diag_capture = True
    _ORIGINAL_PRINT("[JetBot Shopee] request-isolated diagnostic capture enabled")
