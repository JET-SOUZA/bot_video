# youtube_downloader.py
import os
import yt_dlp
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOAD_DIR = SCRIPT_DIR / "downloads" / "youtube"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

def _format_for_quality(quality):
    """
    Retorna string de format do yt-dlp para a quality pedida.
    quality: '360', '480', '720', '1080', '1440', '2160', 'mp3'
    """
    if quality == "mp3":
        return "bestaudio/best"
    try:
        h = int(quality)
    except:
        return "bestvideo+bestaudio/best"
    # combine best video up to height + best audio
    return f"bestvideo[height<={h}]+bestaudio/best"

def download_youtube_file(url: str, quality: str = "480", to_mp3: bool = False, cookiefile: str = None):
    """
    Faz o download (bloqueante). Retorna caminho absoluto do arquivo final.
    - url: link do YouTube
    - quality: '360', '480', '720', '1080', '1440', '2160' ou 'mp3'
    - to_mp3: True -> extrai mp3
    - cookiefile: caminho opcional para cookie
    """
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_title = "%(title)s"
    outtmpl = str(DOWNLOAD_DIR / f"{safe_title}-{timestamp}.%(ext)s")

    ydl_opts = {
        "outtmpl": outtmpl,
        "format": _format_for_quality(quality if not to_mp3 else "mp3"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "postprocessor_args": ["-movflags", "faststart"],
    }

    # If cookies provided (e.g., TikTok/Instagram) - not commonly needed for youtube
    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile

    # If mp3 requested, add audio extractor postprocessor
    if to_mp3 or quality == "mp3":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            },
            {"key": "FFmpegMetadata"},
        ]
        # output filename extension will be .mp3 by prepare_filename for audio extractor
    else:
        # ensure we try to convert/remux to mp4 for video
        ydl_opts.setdefault("postprocessors", [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
            {"key": "FFmpegMetadata"},
        ])

    # run download
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # handle playlist/extractors
        if "entries" in info and info["entries"]:
            info = info["entries"][0]
        filepath = ydl.prepare_filename(info)
        # If mp3 we need to replace extension (yt-dlp will produce .mp3)
        if (to_mp3 or quality == "mp3") and not filepath.lower().endswith(".mp3"):
            # attempt to find .mp3 sibling
            possible = os.path.splitext(filepath)[0] + ".mp3"
            if os.path.exists(possible):
                filepath = possible
        return filepath
