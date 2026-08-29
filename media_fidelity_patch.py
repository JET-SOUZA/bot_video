"""Preserve source media geometry for platforms where yt-dlp already exposes MP4.

X/Twitter normally provides multiple ready-to-play MP4 renditions. Prefer the
highest-quality original rendition that already fits Telegram's bot upload cap;
only fall back to the largest MP4 when no fitting rendition is advertised.
This avoids long FFmpeg work on Render whenever X already exposes a smaller
original stream with the same aspect ratio.
"""

import jetbot_v2 as app


_ORIGINAL_BUILD_GENERAL = app.build_general_ydl_options


def build_general_ydl_options_fidelity(temp_dir, platform, cookiefile=None):
    opts = _ORIGINAL_BUILD_GENERAL(temp_dir, platform, cookiefile)
    if platform == "twitter":
        # Prefer an original muxed MP4 below Telegram's practical 49 MB cap.
        # filesize is authoritative when present; filesize_approx is the next
        # best choice. Only then download the largest original MP4 and let the
        # final Telegram-fit wrapper handle it.
        opts["format"] = (
            "best[ext=mp4][filesize<46M]/"
            "best[ext=mp4][filesize_approx<46M]/"
            "best[ext=mp4]/best"
        )
        opts.pop("format_sort", None)
        opts.pop("merge_output_format", None)
        opts.pop("postprocessors", None)
        opts["socket_timeout"] = 20
        opts["retries"] = 2
        opts["fragment_retries"] = 2
    return opts


app.build_general_ydl_options = build_general_ydl_options_fidelity
print("[JetBot Media] source-fidelity patch loaded (X/Twitter, Telegram-sized original preferred)")
