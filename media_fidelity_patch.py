"""Preserve source media geometry for platforms where yt-dlp already exposes MP4.

X/Twitter normally provides ready-to-play MP4 renditions. Re-encoding every
result through FFmpeg is unnecessary and can make Telegram previews look unlike
the source. This patch asks yt-dlp for the best original MP4 rendition and keeps
its encoded width/height/aspect unchanged.
"""

import jetbot_v2 as app


_ORIGINAL_BUILD_GENERAL = app.build_general_ydl_options


def build_general_ydl_options_fidelity(temp_dir, platform, cookiefile=None):
    opts = _ORIGINAL_BUILD_GENERAL(temp_dir, platform, cookiefile)
    if platform == "twitter":
        # X already serves muxed MP4 variants. Prefer the highest-quality source
        # MP4 and do not run FFmpegVideoConvertor, which is not required here.
        opts["format"] = "best[ext=mp4]/best"
        opts.pop("format_sort", None)
        opts.pop("merge_output_format", None)
        opts.pop("postprocessors", None)
    return opts


app.build_general_ydl_options = build_general_ydl_options_fidelity
print("[JetBot Media] source-fidelity patch loaded (X/Twitter)")
