"""Runtime hardening for yt-dlp on Render.

Loaded automatically by Python (via PYTHONPATH=/app). It injects the
recommended YouTube PO-token provider/client configuration in every yt-dlp
call without changing the public bot flow.
"""

import copy
import os

try:
    import yt_dlp
except Exception:  # pragma: no cover
    yt_dlp = None


if yt_dlp is not None and not getattr(yt_dlp, "_jetbot_runtime_patched", False):
    _OriginalYoutubeDL = yt_dlp.YoutubeDL

    class JetBotYoutubeDL(_OriginalYoutubeDL):
        def __init__(self, params=None, auto_init=True):
            opts = dict(params or {})
            extractor_args = copy.deepcopy(opts.get("extractor_args") or {})

            # Current yt-dlp recommendation: mweb + automatic GVS PO Token.
            # Extra clients are kept as fallbacks because datacenter IP
            # reputation varies and some public videos behave differently.
            youtube_args = dict(extractor_args.get("youtube") or {})
            youtube_args.setdefault(
                "player_client",
                ["mweb", "web_safari", "android_vr", "web_embedded"],
            )
            extractor_args["youtube"] = youtube_args

            # Explicitly point the bgutil provider to the local HTTP server.
            # The Docker image starts it on localhost:4416.
            provider_args = dict(extractor_args.get("youtubepot-bgutilhttp") or {})
            provider_args.setdefault("base_url", ["http://127.0.0.1:4416"])
            extractor_args["youtubepot-bgutilhttp"] = provider_args

            opts["extractor_args"] = extractor_args

            # Optional escape hatch: if a clean proxy is later configured in
            # Render, the bot will use it automatically without another deploy.
            proxy = os.environ.get("YTDLP_PROXY")
            if proxy and not opts.get("proxy"):
                opts["proxy"] = proxy

            super().__init__(opts, auto_init=auto_init)

    yt_dlp.YoutubeDL = JetBotYoutubeDL
    yt_dlp._jetbot_runtime_patched = True
