"""Temporary staging patch that sends sanitized Shopee diagnostics as a text file.

This removes the need to copy screenshots from the Render dashboard while we
finish the Shopee clean-source investigation. The patch only runs for Shopee
links and only sends lines previously captured by shopee_diag_capture.
"""

import io

import jetbot_v2 as app
import shopee_diag_capture


_ORIGINAL_HANDLER = app.baixar_video


async def baixar_video_with_shopee_diag(update, context):
    try:
        return await _ORIGINAL_HANDLER(update, context)
    finally:
        try:
            message = getattr(update, "message", None)
            url = ((getattr(message, "text", None) or "").strip()) if message else ""
            if not url or app.detect_platform(url) != "shopee":
                return
            diagnostics = shopee_diag_capture.pop_shopee_diagnostics()
            if not diagnostics:
                return
            payload = io.BytesIO(diagnostics.encode("utf-8"))
            payload.name = "diagnostico_shopee.txt"
            await message.reply_document(
                document=payload,
                filename="diagnostico_shopee.txt",
                caption="🧪 Diagnóstico Shopee (temporário)",
            )
        except Exception as exc:
            print(f"[JetBot Shopee] diagnostic Telegram delivery failed: {type(exc).__name__}")


app.baixar_video = baixar_video_with_shopee_diag
print("[JetBot Shopee] Telegram diagnostic-file patch loaded")
