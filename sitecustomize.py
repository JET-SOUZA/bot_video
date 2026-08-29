"""YouTube-only runtime hardening for JetBot V2.

Shopee policy is intentionally not patched from sitecustomize. It is applied
explicitly by bootstrap_v2.py so import order cannot silently change which
Shopee downloader is active.
"""

import copy
import os

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
        "failed to extract any player response",
    )
    return any(marker in text for marker in markers)


def _has_cookie_auth(params):
    return bool((params or {}).get("cookiefile") or (params or {}).get("cookiesfrombrowser"))


def _with_strategy(params, client, *, skip_webpage=False, force_pot=False, allow_missing_pot=False):
    opts = copy.deepcopy(params)
    extractor_args = copy.deepcopy(opts.get("extractor_args") or {})
    youtube_args = dict(extractor_args.get("youtube") or {})
    if isinstance(client, (list, tuple)):
        youtube_args["player_client"] = list(client)
    else:
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
    # As of Aug/2026 yt-dlp's default logged-in client (tv_downgraded) can
    # return "The page needs to be reloaded" for valid cookies. Upstream
    # recommends forcing default + web_embedded for cookie-authenticated use.
    # Avoid clients that explicitly do not support account cookies.
    if _has_cookie_auth(base):
        return (
            ("auth-default-web-embedded", _with_strategy(base, ("default", "web_embedded"), force_pot=False)),
            ("auth-web-pot", _with_strategy(base, ("web", "web_embedded"), force_pot=True, allow_missing_pot=True)),
            ("auth-web-creator-pot", _with_strategy(base, "web_creator", force_pot=True, allow_missing_pot=True)),
        )
    return (
        ("web-safari", _with_strategy(base, "web_safari", force_pot=False)),
        ("mweb-pot", _with_strategy(base, "mweb", force_pot=True, allow_missing_pot=True)),
        ("mweb-pot-no-webpage", _with_strategy(base, "mweb", skip_webpage=True, force_pot=True, allow_missing_pot=True)),
        ("web-embedded", _with_strategy(base, "web_embedded", force_pot=False)),
        ("tv", _with_strategy(base, "tv", force_pot=False)),
        ("android-vr", _with_strategy(base, "android_vr", force_pot=True, allow_missing_pot=True)),
    )


def _initial_strategy(base):
    if _has_cookie_auth(base):
        return _with_strategy(base, ("default", "web_embedded"), force_pot=False)
    return _with_strategy(base, "web_safari", force_pot=False)


if yt_dlp is not None and not getattr(yt_dlp, "_jetbot_runtime_patched", False):
    _OriginalYoutubeDL = yt_dlp.YoutubeDL

    class JetBotYoutubeDL(_OriginalYoutubeDL):
        def __init__(self, params=None, auto_init=True):
            base = dict(params or {})
            self._jetbot_base_params = copy.deepcopy(base)
            super().__init__(_initial_strategy(base), auto_init=auto_init)

        def extract_info(self, url, *args, **kwargs):
            try:
                return super().extract_info(url, *args, **kwargs)
            except Exception as first_exc:
                if not _youtube_url(url) or not _retryable_youtube_error(first_exc):
                    raise
                mode = "authenticated" if _has_cookie_auth(self._jetbot_base_params) else "anonymous"
                print(f"[JetBot YT] YouTube extraction blocked/failed; starting {mode} fallback chain...")
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
    print("[JetBot YT] runtime patch loaded (cookie-aware clients + BgUtils PO-token fallbacks)")
