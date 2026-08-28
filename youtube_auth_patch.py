"""Turn YouTube datacenter login challenges into a concise actionable error.

PO tokens solve player-token restrictions but do not replace a valid YouTube
session when Google explicitly challenges the Render IP. The downloader already
supports COOKIES_YOUTUBE / COOKIES_YT_B64; this patch keeps that behavior and
avoids dumping yt-dlp's full exception into Telegram.
"""

import jetbot_v2 as app

_ORIGINAL = app.download_youtube_file_v2


def download_youtube_file_guarded(url, quality="1080", to_mp3=False, cookiefile=None):
    try:
        return _ORIGINAL(url, quality=quality, to_mp3=to_mp3, cookiefile=cookiefile)
    except Exception as exc:
        text = str(exc).lower()
        challenged = any(marker in text for marker in (
            "sign in to confirm you're not a bot",
            "sign in to confirm you’re not a bot",
            "confirm you're not a bot",
            "confirm you’re not a bot",
            "use --cookies-from-browser",
            "use --cookies for the authentication",
        ))
        if challenged:
            has_cookie = bool(app._cookie_payload("youtube"))
            if has_cookie:
                raise RuntimeError(
                    "O YouTube recusou a sessão atual. É necessário renovar os cookies do YouTube no Render."
                ) from None
            raise RuntimeError(
                "O YouTube bloqueou o IP do Render e exigiu login. Adicione COOKIES_YT_B64 nos Secrets do Render para liberar os downloads."
            ) from None
        raise


app.download_youtube_file_v2 = download_youtube_file_guarded
app.legacy.download_youtube_file = download_youtube_file_guarded
print("[JetBot YT] authentication guard patch loaded")
