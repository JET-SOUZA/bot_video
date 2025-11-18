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
    Retorna format correto para cada qualidade:
    360, 480, 720, 1080, 1440, 2160, mp3
    """
    if quality == "mp3":
        return "bestaudio/best"

    try:
        h = int(quality)
    except:
        return "bestvideo+bestaudio/best"

    # match exato da resolução + garantir MP4
    return f"bestvideo[height={h}][ext=mp4]+bestaudio[ext=m4a]/best"


def download_youtube_file(url: str, quality: str = "480", to_mp3: bool = False, cookiefile: str = None):
    """
    Faz download bloqueante. Retorna caminho absoluto.
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

    # SEMPRE usar cookies se existir
    if cookiefile and os.path.exists(cookiefile):
        ydl_opts["cookiefile"] = cookiefile

    # MP3 mode
    if to_mp3 or quality == "mp3":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts.pop("merge_output_format", None)  # evitar erro
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            },
            {"key": "FFmpegMetadata"},
        ]

    else:
        # garantir pós-processamento correto para vídeo
        ydl_opts.setdefault(
            "postprocessors",
            [
                {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
                {"key": "FFmpegMetadata"},
            ]
        )

    # Execute download
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        # playlist fallback
        if "entries" in info:
            info = info["entries"][0]

        filepath = ydl.prepare_filename(info)

        # Ajuste MP3
        if (to_mp3 or quality == "mp3") and not filepath.lower().endswith(".mp3"):
            alt = os.path.splitext(filepath)[0] + ".mp3"
            if os.path.exists(alt):
                filepath = alt

        return filepath
