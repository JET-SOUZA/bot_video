"""Runtime hardening for yt-dlp on Render.

Python imports this module automatically. It keeps the public bot flow intact,
but applies YouTube-specific runtime settings and retries extraction with
clients that can avoid the initial youtube.com webpage request when a Render
/datacenter IP receives the "Sign in to confirm you're not a bot" block.
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


def _auth_ip_block(exc):
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "sign in to confirm you",
            "confirm you're not a bot",
            "confirm you’re not a bot",
            "use --cookies-from-browser",
            "use --cookies for the authentication",
        )
    )


def _with_strategy(params, client, *, skip_webpage=False, disable_innertube=False):
    opts = copy.deepcopy(params)
    extractor_args = copy.deepcopy(opts.get("extractor_args") or {})

    youtube_args = dict(extractor_args.get("youtube") or {})
    youtube_args["player_client"] = [client]
    # Skipping the initial webpage is important on datacenter IPs where the
    # public watch page itself is what returns the anti-bot interstitial.
    if skip_webpage:
        youtube_args["player_skip"] = ["webpage"]
    else:
        youtube_args.pop("player_skip", None)
    # Helpful while validating the PO-token path in Render logs.
    youtube_args["pot_trace"] = ["true"]
    extractor_args["youtube"] = youtube_args

    provider_args = dict(extractor_args.get("youtubepot-bgutilhttp") or {})
    provider_args["base_url"] = ["http://127.0.0.1:4416"]
    if disable_innertube:
        provider_args["disable_innertube"] = ["1"]
    else:
        provider_args.pop("disable_innertube", None)
    extractor_args["youtubepot-bgutilhttp"] = provider_args

    opts["extractor_args"] = extractor_args
    opts["force_ipv4"] = True

    proxy = os.environ.get("YTDLP_PROXY")
    if proxy:
        opts["proxy"] = proxy

    # Keep normal bot output quiet; diagnostic retry names are printed below.
    opts.setdefault("quiet", True)
    return opts


if yt_dlp is not None and not getattr(yt_dlp, "_jetbot_runtime_patched", False):
    _OriginalYoutubeDL = yt_dlp.YoutubeDL

    class JetBotYoutubeDL(_OriginalYoutubeDL):
        def __init__(self, params=None, auto_init=True):
            base = dict(params or {})
            # Recommended first attempt: mweb + automatic BgUtils GVS PO Token.
            opts = _with_strategy(base, "mweb")
            self._jetbot_base_params = copy.deepcopy(base)
            super().__init__(opts, auto_init=auto_init)

        def extract_info(self, url, *args, **kwargs):
            try:
                return super().extract_info(url, *args, **kwargs)
            except Exception as first_exc:
                if not _youtube_url(url) or not _auth_ip_block(first_exc):
                    raise

                print("[JetBot YT] Render IP block detected; trying no-webpage strategies...")
                last_exc = first_exc

                # Each retry is a fresh yt-dlp instance. This matters because a
                # failed extractor can retain guest/session state internally.
                # mweb uses the local PO-token server; android_vr/tv are useful
                # fallbacks because they currently do not require a GVS token.
                strategies = (
                    ("mweb-no-webpage", "mweb", True, False),
                    ("mweb-legacy-provider", "mweb", True, True),
                    ("android-vr-no-webpage", "android_vr", True, False),
                    ("tv-no-webpage", "tv", True, False),
                    ("web-embedded-no-webpage", "web_embedded", True, False),
                )

                for label, client, skip_webpage, disable_innertube in strategies:
                    retry_opts = _with_strategy(
                        self._jetbot_base_params,
                        client,
                        skip_webpage=skip_webpage,
                        disable_innertube=disable_innertube,
                    )
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
    print("[JetBot YT] runtime patch loaded (PO token + anti-bot fallbacks)")
