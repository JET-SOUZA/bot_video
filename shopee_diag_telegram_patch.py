"""Optional staging delivery of sanitized, request-local Shopee diagnostics.

Disabled by default. Set SHOPEE_DIAGNOSTICS=1 only on the staging service when
we need a diagnostic file. Production users never receive diagnostico_shopee.txt.
"""

import io
import os

import jetbot_v2 as app
import shopee_diag_capture

_ENABLED = os.getenv("SHOPEE_DIAGNOSTICS", "0").strip().lower() in {"1", "true", "yes", "on"}
_ORIGINAL_HANDLER = app.baixar_video


async def baixar_video_with_shopee_diag(update, context):
    message = getattr(update, "message", None)
    url = ((getattr(message, "text", None) or "").strip()) if message else ""
    is_shopee = bool(url and app.detect_platform(url) == "shopee")
    token = shopee_diag_capture.begin_shopee_diagnostics() if (_ENABLED and is_shopee) else None
    try:
        return await _ORIGINAL_HANDLER(update, context)
    finally:
        diagnostics = shopee_diag_capture.end_shopee_diagnostics(token)
        if not diagnostics or not message:
            return
        try:
            payload = io.BytesIO(diagnostics.encode("utf-8"))
            payload.name = "diagnostico_shopee.txt"
            await message.reply_document(
                document=payload,
                filename="diagnostico_shopee.txt",
                caption="🧪 Diagnóstico Shopee (staging)",
            )
        except Exception as exc:
            print(f"[JetBot Shopee] diagnostic Telegram delivery failed: {type(exc).__name__}")


if _ENABLED:
    app.baixar_video = baixar_video_with_shopee_diag
    print("[JetBot Shopee] Telegram diagnostic-file patch enabled for staging")
