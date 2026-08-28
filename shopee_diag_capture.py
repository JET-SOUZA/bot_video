"""Temporary staging helper: capture only sanitized JetBot Shopee diagnostics.

This module mirrors stdout normally and keeps a small in-memory buffer of lines
that start with ``[JetBot Shopee]``. It never captures unrelated application
logs. Long opaque tokens and raw URLs are redacted again as a defense-in-depth
measure before the text is exposed to the Telegram staging tester.
"""

import builtins
import re
import threading
from collections import deque

_LOCK = threading.Lock()
_LINES = deque(maxlen=240)
_ORIGINAL_PRINT = builtins.print


def _sanitize(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"https?://[^\s\"']+", "<URL>", text)
    text = re.sub(r"[A-Za-z0-9_\-]{80,}", "<LONG_TOKEN>", text)
    return text[:700]


def _capture_print(*args, **kwargs):
    try:
        rendered = " ".join(str(arg) for arg in args)
        if rendered.startswith("[JetBot Shopee]"):
            with _LOCK:
                _LINES.append(_sanitize(rendered))
    except Exception:
        pass
    return _ORIGINAL_PRINT(*args, **kwargs)


def pop_shopee_diagnostics() -> str:
    """Return and clear the currently buffered Shopee-only diagnostic lines."""
    with _LOCK:
        if not _LINES:
            return ""
        text = "\n".join(_LINES)
        _LINES.clear()
    return text + "\n"


if not getattr(builtins, "_jetbot_shopee_diag_capture", False):
    builtins.print = _capture_print
    builtins._jetbot_shopee_diag_capture = True
