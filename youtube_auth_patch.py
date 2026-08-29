"""Turn YouTube datacenter login challenges into concise actionable errors.

PO tokens solve player-token restrictions but do not replace a valid YouTube
session when Google explicitly challenges the Render IP. The downloader already
supports COOKIES_YOUTUBE / COOKIES_YT_B64; this patch keeps that behavior and
avoids dumping yt-dlp's full exception into Telegram.
"""

import jetbot_v2 as app

_ORIGINAL = app.download_youtube_file_v2

# Cookies that are strong signals of an authenticated Google/YouTube session.
# We only inspect cookie *names* in memory; values are never logged.
_AUTH_COOKIE_MARKERS = (
    "\tSAPISID\t",
    "\tAPISID\t",
    "\tSID\t",
    "\tHSID\t",
    "\tSSID\t",
    "\tLOGIN_INFO\t",
    "\t__Secure-1PSID\t",
    "\t__Secure-3PSID\t",
    "\t__Secure-1PAPISID\t",
    "\t__Secure-3PAPISID\t",
)


def _cookie_session_state():
    payload = app._cookie_payload("youtube") or ""
    if not payload:
        return "missing"
    # Netscape files are tab-separated. Requiring an auth-cookie name avoids
    # treating anonymous VISITOR/YSC/PREF cookies as a logged-in session.
    if any(marker in payload for marker in _AUTH_COOKIE_MARKERS):
        return "authenticated"
    return "anonymous"


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
            state = _cookie_session_state()
            if state == "anonymous":
                raise RuntimeError(
                    "Os cookies enviados estão em formato válido, mas não pertencem a uma sessão logada do YouTube. Entre na conta no Orion e exporte novamente os cookies do YouTube."
                ) from None
            if state == "authenticated":
                raise RuntimeError(
                    "O YouTube recusou a sessão autenticada atual. Renove os cookies do YouTube no Render e tente novamente."
                ) from None
            raise RuntimeError(
                "O YouTube bloqueou o IP do Render e exigiu login. Adicione COOKIES_YT_B64 nos Secrets do Render para liberar os downloads."
            ) from None
        raise


app.download_youtube_file_v2 = download_youtube_file_guarded
app.legacy.download_youtube_file = download_youtube_file_guarded
print("[JetBot YT] authentication guard patch loaded")
