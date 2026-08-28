"""Runtime hardening for JetBot V2.

Keeps the public bot flow intact while applying YouTube-specific runtime
settings and a Shopee Video clean-source resolver for short/share links.
"""

import builtins
import copy
import json
import os
import re
import sys
from urllib.parse import quote, urlsplit, urlunsplit

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

try:
    import yt_dlp
except Exception:  # pragma: no cover
    yt_dlp = None


def _youtube_url(value):
    text = str(value or "").lower()
    return "youtube.com" in text or "youtu.be" in text


def _retryable_youtube_error(exc):
    text = str(exc).lower()
    markers = (
        "sign in to confirm you",
        "confirm you're not a bot",
        "confirm you’re not a bot",
        "use --cookies-from-browser",
        "use --cookies for the authentication",
        "http error 403",
        "forbidden",
        "requested format is not available",
        "no video formats found",
        "the page needs to be reloaded",
    )
    return any(marker in text for marker in markers)


def _with_strategy(params, client, *, skip_webpage=False, force_pot=False, allow_missing_pot=False):
    opts = copy.deepcopy(params)
    extractor_args = copy.deepcopy(opts.get("extractor_args") or {})
    youtube_args = dict(extractor_args.get("youtube") or {})
    youtube_args["player_client"] = [client]
    if skip_webpage:
        youtube_args["player_skip"] = ["webpage"]
    else:
        youtube_args.pop("player_skip", None)
    if force_pot:
        youtube_args["fetch_pot"] = ["always"]
    else:
        youtube_args.pop("fetch_pot", None)
    if allow_missing_pot:
        youtube_args["formats"] = ["missing_pot"]
    else:
        youtube_args.pop("formats", None)
    youtube_args["pot_trace"] = ["true"]
    extractor_args["youtube"] = youtube_args
    provider_args = dict(extractor_args.get("youtubepot-bgutilhttp") or {})
    provider_args["base_url"] = ["http://127.0.0.1:4416"]
    provider_args.pop("disable_innertube", None)
    extractor_args["youtubepot-bgutilhttp"] = provider_args
    opts["extractor_args"] = extractor_args
    opts["force_ipv4"] = True
    proxy = os.environ.get("YTDLP_PROXY")
    if proxy:
        opts["proxy"] = proxy
    opts.setdefault("quiet", True)
    opts.setdefault("no_warnings", False)
    return opts


def _strategy_chain(base):
    return (
        ("web-safari", _with_strategy(base, "web_safari", force_pot=False)),
        ("mweb-pot", _with_strategy(base, "mweb", force_pot=True, allow_missing_pot=True)),
        ("mweb-pot-no-webpage", _with_strategy(base, "mweb", skip_webpage=True, force_pot=True, allow_missing_pot=True)),
        ("web-embedded", _with_strategy(base, "web_embedded", force_pot=False)),
        ("tv", _with_strategy(base, "tv", force_pot=False)),
        ("android-vr", _with_strategy(base, "android_vr", force_pot=True, allow_missing_pot=True)),
    )


if yt_dlp is not None and not getattr(yt_dlp, "_jetbot_runtime_patched", False):
    _OriginalYoutubeDL = yt_dlp.YoutubeDL

    class JetBotYoutubeDL(_OriginalYoutubeDL):
        def __init__(self, params=None, auto_init=True):
            base = dict(params or {})
            self._jetbot_base_params = copy.deepcopy(base)
            first = _with_strategy(base, "web_safari", force_pot=False)
            super().__init__(first, auto_init=auto_init)

        def extract_info(self, url, *args, **kwargs):
            try:
                return super().extract_info(url, *args, **kwargs)
            except Exception as first_exc:
                if not _youtube_url(url) or not _retryable_youtube_error(first_exc):
                    raise
                print("[JetBot YT] YouTube extraction blocked/failed; starting fallback chain...")
                last_exc = first_exc
                for label, retry_opts in _strategy_chain(self._jetbot_base_params):
                    print(f"[JetBot YT] retry={label}")
                    try:
                        with _OriginalYoutubeDL(retry_opts) as retry_ydl:
                            result = retry_ydl.extract_info(url, *args, **kwargs)
                        print(f"[JetBot YT] success={label}")
                        return result
                    except Exception as retry_exc:
                        last_exc = retry_exc
                        print(f"[JetBot YT] failed={label}: {type(retry_exc).__name__}: {retry_exc}")
                raise last_exc

    yt_dlp.YoutubeDL = JetBotYoutubeDL
    yt_dlp._jetbot_runtime_patched = True
    print("[JetBot YT] runtime patch loaded (web_safari + BgUtils PO-token fallbacks)")


# ---------------------------------------------------------------------------
# Shopee Video: clean source resolver
# ---------------------------------------------------------------------------
_SHOPEE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
    "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
)


def _iter_shopee_media(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            yield from _iter_shopee_media(item, child)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _iter_shopee_media(item, f"{path}[{index}]")
    elif isinstance(value, str):
        candidate = value.replace("\\u002F", "/").replace("\\/", "/").replace("&amp;", "&")
        if candidate.startswith("//"):
            candidate = "https:" + candidate
        low = candidate.lower()
        if candidate.startswith("http") and any(token in low for token in (".mp4", ".m3u8", "video", "play")):
            yield path.lower(), candidate


def _shopee_rank(path, url):
    text = f"{path} {url}".lower()
    score = 0
    for hint, points in (
        ("original", 240), ("origin", 220), ("source", 180), ("raw", 170),
        ("upload", 150), ("master", 130), ("download", 100), ("video_url", 90),
        ("play_url", 70), (".mp4", 45), ("h265", 25), ("hevc", 25),
    ):
        if hint in text:
            score += points
    for hint, points in (
        ("watermark", 500), ("watermarked", 500), ("with_watermark", 500),
        ("logo", 300), ("preview", 180), ("thumb", 300), ("cover", 300),
        ("render", 130), ("transcode", 60),
    ):
        if hint in text:
            score -= points
    return score


def _mark_original_hint(url):
    """Adds a harmless query hint so JetBot V2 ranks this fallback as original."""
    try:
        parts = urlsplit(url)
        query = parts.query
        query = f"{query}&jetbot_original=1" if query else "jetbot_original=1"
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
    except Exception:
        return url


def _extract_next_payloads(html, resolved, share_id, headers):
    payloads = []
    try:
        match = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.S | re.I)
        if match:
            data = json.loads(match.group(1))
            payloads.append(("next_data", data))
            build_id = data.get("buildId") if isinstance(data, dict) else None
            if build_id and requests is not None:
                encoded = quote(share_id, safe="")
                data_urls = (
                    f"https://sv.shopee.com.br/share-web/_next/data/{build_id}/share-video/{encoded}.json",
                    f"https://sv.shopee.com.br/_next/data/{build_id}/share-video/{encoded}.json",
                )
                for data_url in data_urls:
                    try:
                        r = requests.get(data_url, timeout=12, headers=headers)
                        if r.ok and "json" in (r.headers.get("content-type") or "").lower():
                            payloads.append(("next_json", r.json()))
                    except Exception:
                        pass
    except Exception:
        pass
    return payloads


def _resolve_shopee_clean(url):
    if requests is None:
        return None
    headers = {
        "User-Agent": _SHOPEE_UA,
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Referer": "https://sv.shopee.com.br/",
    }
    try:
        response = requests.get(url, allow_redirects=True, timeout=15, headers=headers)
        resolved = response.url
        html = response.text or ""
    except Exception:
        return None

    share = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", resolved)
    if not share:
        share = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", html)
    if not share:
        return None
    share_id = share.group(1)

    candidates = []
    for label, payload in _extract_next_payloads(html, resolved, share_id, headers):
        for path, candidate in _iter_shopee_media(payload):
            candidates.append((f"{label}.{path}", candidate))

    # Scan hydrated HTML too. Shopee often serializes media URLs in page props.
    for match in re.finditer(r"https?:\\?/\\?/[^\s\"'<>]+", html):
        raw = match.group(0).replace("\\u002F", "/").replace("\\/", "/")
        if any(token in raw.lower() for token in (".mp4", ".m3u8", "video", "play")):
            candidates.append(("html", raw))

    dedup = {}
    for path, candidate in candidates:
        if not candidate.startswith("http"):
            continue
        score = _shopee_rank(path, candidate)
        if candidate not in dedup or score > dedup[candidate]:
            dedup[candidate] = score
    if not dedup:
        return None

    ranked = sorted(dedup.items(), key=lambda item: item[1], reverse=True)
    best, score = ranked[0]
    print(f"[JetBot Shopee] share_id={share_id} candidates={len(ranked)} best_score={score}")
    return _mark_original_hint(best)


def _patch_legacy_shopee(module):
    if module is None or getattr(module, "_jetbot_shopee_patched", False):
        return
    original = getattr(module, "extrair_video_shopee", None)
    if not callable(original):
        return

    def clean_first(url):
        try:
            clean = _resolve_shopee_clean(url)
            if clean:
                print("[JetBot Shopee] clean Next.js source selected")
                return clean
        except Exception as exc:
            print(f"[JetBot Shopee] clean resolver failed: {type(exc).__name__}: {exc}")
        return original(url)

    module.extrair_video_shopee = clean_first
    module._jetbot_shopee_patched = True
    print("[JetBot Shopee] legacy extractor patched (clean-source first)")


# bot.py is imported after sitecustomize, so patch it immediately after import.
_original_import = builtins.__import__


def _jetbot_import(name, globals=None, locals=None, fromlist=(), level=0):
    module = _original_import(name, globals, locals, fromlist, level)
    if name == "bot" or name.endswith(".bot"):
        _patch_legacy_shopee(sys.modules.get("bot"))
    return module


if not getattr(builtins, "_jetbot_import_patched", False):
    builtins.__import__ = _jetbot_import
    builtins._jetbot_import_patched = True
