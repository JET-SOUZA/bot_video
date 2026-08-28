"""JetBot V2 runtime entrypoint.

Aplica uma política estrita para Shopee Video: nunca entrega como original
uma URL que veio de campo/rota marcada como watermark. Se a página pública
só expuser a versão carimbada, o bot falha com mensagem clara em vez de
baixar a versão marcada silenciosamente.
"""

import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests
import yt_dlp

import jetbot_v2 as app


BAD_SHOPEE_HINTS = (
    "watermark",
    "watermarked",
    "watermarkvideourl",
    "watermark_video",
    "play_watermark",
    "preview",
    "rendered",
    "logo",
    "cover",
    "thumb",
)

GOOD_SHOPEE_HINTS = (
    "original",
    "originalvideourl",
    "original_video",
    "origin",
    "source",
    "master",
    "raw",
    "upload",
    "download",
    "video_url",
    "play_url",
)


def _marked_candidate(path: str, url: str) -> bool:
    text = f"{path} {url}".lower()
    return any(hint in text for hint in BAD_SHOPEE_HINTS)


def _clean_score(path: str, url: str) -> int:
    text = f"{path} {url}".lower()
    score = app._rank_shopee_candidate(path, url)
    for hint in GOOD_SHOPEE_HINTS:
        if hint in text:
            score += 50
    if ".mp4" in text:
        score += 20
    return score


def _external_clean_source(url: str):
    """Usa somente um extrator configurado pelo dono do bot.

    Não há endpoint de terceiro embutido. Se SHOPEE_EXTRACTOR_URL existir,
    espera JSON no formato {success, videoUrl} ou {videoUrl}.
    """
    endpoint = (os.environ.get("SHOPEE_EXTRACTOR_URL") or "").strip()
    if not endpoint:
        return None
    try:
        response = requests.post(endpoint, json={"url": url}, timeout=20)
        response.raise_for_status()
        payload = response.json()
        candidate = payload.get("videoUrl") or payload.get("video_url") or payload.get("url")
        if not candidate or not str(candidate).startswith("http"):
            return None
        if _marked_candidate("external.videoUrl", str(candidate)):
            return None
        return str(candidate)
    except Exception as exc:
        print(f"[JetBot Shopee] external extractor failed: {type(exc).__name__}: {exc}")
        return None


def strict_extract_shopee_original(url: str):
    resolved = app._resolve_shopee(url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Referer": "https://sv.shopee.com.br/",
    }
    candidates = []
    html = ""

    try:
        page = requests.get(resolved, timeout=15, headers=headers)
        if page.ok:
            html = page.text
    except Exception as exc:
        print(f"[JetBot Shopee] page fetch failed: {type(exc).__name__}: {exc}")

    share_match = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", resolved)
    if not share_match and html:
        share_match = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", html)

    if share_match:
        share_id = share_match.group(1)
        for version in ("v4", "v2"):
            api_url = f"https://sv.shopee.com.br/api/{version}/share/video?shareVideoId={share_id}"
            try:
                response = requests.get(api_url, timeout=15, headers=headers)
                if response.ok:
                    candidates.extend(app._iter_media_candidates(response.json()))
            except Exception as exc:
                print(f"[JetBot Shopee] {version} share API failed: {type(exc).__name__}: {exc}")

    if html:
        # Mantém o nome do campo para sabermos se a URL veio de watermarkVideoUrl.
        field_pattern = re.compile(
            r'"([^"\\]*(?:original|origin|source|master|raw|upload|download|play|video|watermark)[^"\\]*)"\s*:\s*"(https?:[^"\\]+)"',
            flags=re.IGNORECASE,
        )
        for match in field_pattern.finditer(html):
            raw = match.group(2).replace("\\u002F", "/").replace("\\/", "/")
            candidates.append((match.group(1).lower(), raw))

        for match in re.finditer(r"https?:\\?/\\?/[^\s\"'<>]+?(?:\.mp4|\.m3u8)[^\s\"'<>]*", html):
            raw = match.group(0).replace("\\/", "/")
            candidates.append(("html.unlabeled", raw))

    unique = {}
    for path, candidate in candidates:
        if not candidate or not str(candidate).startswith("http"):
            continue
        candidate = str(candidate)
        marked = _marked_candidate(path, candidate)
        score = _clean_score(path, candidate)
        current = unique.get(candidate)
        if current is None or score > current[0]:
            unique[candidate] = (score, marked, path)

    ranked = sorted(
        ((url_value, *meta) for url_value, meta in unique.items()),
        key=lambda item: item[1],
        reverse=True,
    )

    for candidate, score, marked, path in ranked[:12]:
        host = urlparse(candidate).netloc
        print(
            f"[JetBot Shopee] candidate path={path} score={score} marked={marked} host={host}"
        )

    clean = [item for item in ranked if not item[2]]
    if clean:
        candidate, score, _marked, path = clean[0]
        print(f"[JetBot Shopee] clean source selected path={path} score={score}")
        return candidate

    external = _external_clean_source(url)
    if external:
        print("[JetBot Shopee] clean source selected from configured extractor")
        return external

    print("[JetBot Shopee] CLEAN_SOURCE_NOT_FOUND: only marked/untrusted sources were exposed")
    return None


def strict_download_media(url: str, uid: int):
    platform = app.detect_platform(url)
    if platform != "shopee":
        return _original_download_media(url, uid)

    temp_dir = Path(tempfile.mkdtemp(prefix=f"jetbot-{uid}-", dir=app.DOWNLOADS_DIR))
    cookiefile = app._temporary_cookiefile("shopee")
    try:
        clean_url = strict_extract_shopee_original(url)
        if not clean_url:
            raise RuntimeError(
                "A Shopee só expôs a versão com marca para este link; o bot não vai enviar uma cópia marcada como original."
            )

        if ".m3u8" in clean_url.lower():
            opts = app.build_general_ydl_options(temp_dir, "shopee", cookiefile)
            opts["outtmpl"] = str(temp_dir / "shopee-clean.%(ext)s")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(clean_url, download=True)
            media = app._find_media(temp_dir, ".mp4")
            title = (info or {}).get("title") or "Shopee Vídeo"
        else:
            media = app._download_direct(clean_url, temp_dir / "shopee-clean.mp4")
            title = "Shopee Vídeo"

        if not media or not Path(media).exists():
            raise RuntimeError("A fonte limpa foi localizada, mas o arquivo final não foi criado.")

        return {
            "path": str(media),
            "title": title,
            "platform": "shopee",
            "temp_dir": str(temp_dir),
            "source": "shopee-clean-strict",
        }
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    finally:
        app._safe_unlink(cookiefile)


_original_download_media = app.download_media
app._extract_shopee_original_url = strict_extract_shopee_original
app.download_media = strict_download_media


if __name__ == "__main__":
    app.main()
