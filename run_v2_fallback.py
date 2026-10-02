"""JetBot V2 strict Shopee policy layer.

Only a positively identified clean/original source may reach the downloader.
Watermarked renditions are never used as a fallback, including when an
environment variable is set accidentally in production.

Runtime bindings are applied explicitly by apply_runtime_policy(); importing
this module alone no longer mutates jetbot_v2 global functions.
"""

import contextvars
import re
from pathlib import Path
from urllib.parse import urlparse

import run_v2 as runtime


_ORIGINAL_EXTRACT = runtime.strict_extract_shopee_original
_ALLOW_MARKED_FALLBACK = False
_SOURCE_KIND = contextvars.ContextVar("jetbot_shopee_source_kind", default=None)
_RUNTIME_APPLIED = False


def _normalize_media_url(value):
    if not isinstance(value, str):
        return None
    value = value.replace("\\u002F", "/").replace("\\/", "/").replace("&amp;", "&")
    if value.startswith("//"):
        value = "https:" + value
    if not value.startswith("http"):
        return None
    low = value.lower()
    if ".mp4" in low or ".m3u8" in low:
        return value
    return None


def _fallback_score(path, url):
    text = f"{path} {url}".lower()
    score = 0
    if "watermarkvideourl" in text or "watermark_video_url" in text:
        score += 320
    if "verified_original_source" in text or "original" in text or "source" in text:
        score += 360
    if path.lower().endswith(".url") or ".video.url" in path.lower():
        score += 240
    if ".mp4" in text:
        score += 120
    if ".m3u8" in text:
        score += 100
    if "vod.susercontent.com" in text:
        score += 40
    if any(token in text for token in ("cover", "thumb", "thumbnail", "image", "avatar")):
        score -= 1000
    return score


def _select_playable_candidate(candidates):
    unique = {}
    for path, value in candidates:
        url = _normalize_media_url(value)
        if not url:
            continue
        score = _fallback_score(path, url)
        current = unique.get(url)
        if current is None or score > current[0]:
            unique[url] = (score, path)
    if not unique:
        return None
    ranked = sorted(unique.items(), key=lambda item: item[1][0], reverse=True)
    for url, (score, path) in ranked:
        if score <= -500:
            continue
        parsed = urlparse(url)
        leaf = Path(parsed.path).name[:80] or "/"
        print(
            f"[JetBot Shopee] playable fallback candidate path={path} "
            f"score={score} host={parsed.netloc} file={leaf}"
        )
        return url
    return None


def _fallback_shopee_media(url):
    resolved = runtime.app._resolve_shopee(url)
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
        page = runtime.requests.get(resolved, timeout=15, headers=headers)
        if page.ok:
            html = page.text or ""
            resolved = getattr(page, "url", None) or resolved
    except Exception as exc:
        print(f"[JetBot Shopee] fallback page fetch failed: {type(exc).__name__}: {exc}")

    share_id = runtime._extract_shopee_share_id(resolved, html)

    if share_id:
        for version in ("v4", "v2"):
            api_url = f"https://sv.shopee.com.br/api/{version}/share/video?shareVideoId={share_id}"
            try:
                response = runtime.requests.get(api_url, timeout=15, headers=headers)
                if response.ok:
                    for path, candidate in runtime.app._iter_media_candidates(response.json()):
                        candidates.append((f"api.{version}.{path}", candidate))
            except Exception as exc:
                print(f"[JetBot Shopee] fallback {version} API failed: {type(exc).__name__}: {exc}")

        if html:
            for label, payload in runtime._iter_next_payloads(html, share_id, headers):
                for path, candidate in runtime.app._iter_media_candidates(payload):
                    candidates.append((f"{label}.{path}", candidate))

    if html:
        field_pattern = re.compile(
            r'"([^"\\]*(?:watermarkvideourl|watermark_video_url|original|source|master|play|video|url)[^"\\]*)"\s*:\s*"(https?:[^"\\]+)"',
            flags=re.IGNORECASE,
        )
        for match in field_pattern.finditer(html):
            raw = match.group(2).replace("\\u002F", "/").replace("\\/", "/")
            candidates.append((f"html.field.{match.group(1).lower()}", raw))

        for match in re.finditer(r"https?:\\?/\\?/[^\s\"'<>]+?(?:\.mp4|\.m3u8)[^\s\"'<>]*", html):
            candidates.append(("html.playable", match.group(0).replace("\\/", "/")))

    return _select_playable_candidate(candidates)


def extract_shopee_prefer_original(url):
    _SOURCE_KIND.set(None)
    clean = _ORIGINAL_EXTRACT(url)
    if clean:
        _SOURCE_KIND.set("clean")
        print("[JetBot Shopee] source_kind=clean")
        return clean

    # Deliberately do not call _fallback_shopee_media here.  It remains a
    # diagnostics helper for inspecting public payloads, but no marked or
    # untrusted candidate can enter the production download path.
    print("[JetBot Shopee] original unavailable; marked fallback blocked by strict policy")
    return None


def download_media_with_shopee_policy(url, uid):
    """Run the strict downloader and attach truthful Shopee source metadata."""
    token = _SOURCE_KIND.set(None)
    try:
        result = runtime.strict_download_media(url, uid)
        if runtime.app.detect_platform(url) != "shopee" or not isinstance(result, dict):
            return result
        kind = _SOURCE_KIND.get()
        result = dict(result)
        if kind == "clean":
            result["source"] = "shopee-clean"
            result["watermarked"] = False
        else:
            result["source"] = "shopee-unknown"
            result["watermarked"] = None
        return result
    finally:
        _SOURCE_KIND.reset(token)


def apply_runtime_policy():
    """Apply the final Shopee + Telegram wrapper chain exactly once."""
    global _RUNTIME_APPLIED
    runtime.strict_extract_shopee_original = extract_shopee_prefer_original
    runtime.app._extract_shopee_original_url = extract_shopee_prefer_original
    runtime.app.download_media = download_media_with_shopee_policy

    import telegram_fit_patch as _telegram_fit
    _telegram_fit._ORIGINAL_DOWNLOAD_MEDIA = download_media_with_shopee_policy
    runtime.app.download_media = _telegram_fit.download_media_with_telegram_fit
    _RUNTIME_APPLIED = True
    print("[JetBot Media] explicit Shopee policy + Telegram size-fit runtime applied")


if __name__ == "__main__":
    apply_runtime_policy()
    runtime.app.main()
