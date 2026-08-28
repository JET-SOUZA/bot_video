"""Runtime hardening for yt-dlp on Render.

Keeps the public bot flow intact while applying YouTube-specific runtime
settings. The retry chain is designed for datacenter IPs and prefers current
2026 yt-dlp strategies: HLS-capable web_safari, then mweb with an automatic
BgUtils PO-token provider, followed by conservative embedded/TV fallbacks.
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

    # Current yt-dlp supports automatic provider-backed token retrieval.
    # fetch_pot=always asks the provider to mint a token whenever applicable;
    # formats=missing_pot prevents yt-dlp from hiding formats before the
    # provider has a chance to supply the required token.
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
    # Do NOT pass disable_innertube: it was removed by bgutil 1.3.x.
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
    # web_safari can expose HLS formats that currently do not require a GVS
    # PO token, so it is a valuable first fallback on blocked datacenter IPs.
    # mweb is the recommended provider-backed client for full formats.
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
            # Start with web_safari instead of mweb. This gives HLS a chance to
            # work without a GVS token and avoids immediately hitting a broken
            # mweb path on some Render IPs.
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
