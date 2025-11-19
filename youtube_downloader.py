# youtube_downloader.py
import os
import yt_dlp
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOAD_DIR = SCRIPT_DIR / "downloads" / "youtube"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _format_for_quality(quality):
    """Retorna o format adequado ao nível pedido."""
    if quality == "mp3":
        return "bestaudio/best"

    try:
        h = int(quality)
    except:
        return "bv*+ba/b"

    return f"bv*[height<={h}]+ba/b"


def download_youtube_file(url: str, quality: str = "480", to_mp3: bool = False, cookiefile: str = None):
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

        # 🔥 Aceleração real:
        "concurrent_fragment_downloads": True,
        "concurrent_fragment_downloads_count": 10,
        "fragment_retries": 999,
        "retries": 999,

        # 🔥 Melhor conexão FFmpeg
        "downloader": "ffmpeg",
        "downloader_args": {
            "ffmpeg_i": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
        },
    }

    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile

    # --- MP3 ---
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

    else:
        # --- Conversão correta para MP4 ---
         ydl_opts["postprocessors"] = [
    {
        "key": "FFmpegVideoConvertor",
        "preferedformat": "mp4"   # <- correto (com 1 'r')
    },
    {"key": "FFmpegMetadata"}
]

    # Executa o download
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        if "entries" in info and info["entries"]:
            info = info["entries"][0]

        filepath = ydl.prepare_filename(info)

        # Ajuste caso MP3
        if (to_mp3 or quality == "mp3") and not filepath.lower().endswith(".mp3"):
            mp3 = os.path.splitext(filepath)[0] + ".mp3"
            if os.path.exists(mp3):
                filepath = mp3

        return filepath
