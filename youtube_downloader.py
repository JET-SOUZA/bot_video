# youtube_downloader.py
# Lightweight YouTube downloader WITHOUT MERGE (Render-safe)
# Downloads only one stream directly (video-only, audio-only, or mixed)

import yt_dlp
import os
from pathlib import Path
from datetime import datetime


def download_youtube_file(url, quality="360", to_mp3=False, cookiefile=None):
    """
    Render-SAFE YouTube downloader.
    - No ffmpeg
    - No merge
    - Downloads only one direct stream
    """

    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    outdir = Path("downloads")
    outdir.mkdir(exist_ok=True)

    # Saída segura (sem depender de ID do YouTube)
    if to_mp3:
        filename = outdir / f"yt-{ts}.%(ext)s"
    else:
        filename = outdir / f"yt-{quality}-{ts}.%(ext)s"

    # Mapeamento de qualidades diretamente do YouTube (sem merge)
    FORMATS = {
        "mp3": "bestaudio/best",
        "360": "best[height<=360][ext=mp4]/best[height<=360]",
        "480": "best[height<=480][ext=mp4]/best[height<=480]",
        "720": "best[height<=720]/bestvideo[height<=720]",
        "1080": "best[height<=1080]/bestvideo[height<=1080]",
        "1440": "best[height<=1440]/bestvideo[height<=1440]",
        "2160": "best[height<=2160]/bestvideo[height<=2160]",
    }

    selected_format = FORMATS.get(quality, FORMATS["360"])

    ydl_opts = {
        "outtmpl": str(filename),
        "format": selected_format,
        "quiet": True,
        "noplaylist": True,
        "nocheckcertificate": True,
    }

    # Cookies (se existirem)
    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile

    # Se for MP3 → baixar só o áudio (sem converter)
    if to_mp3:
        ydl_opts["format"] = "bestaudio/best"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    final_path = ydl.prepare_filename(info)

    return final_path
