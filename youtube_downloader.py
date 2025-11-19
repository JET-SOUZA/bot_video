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


class SilentLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): print(msg)


def download_youtube_file(url: str, quality: str = "480", to_mp3: bool = False, cookiefile: str = None):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_title = "%(title)s"
    outtmpl = str(DOWNLOAD_DIR / f"{safe_title}-{timestamp}.%(ext)s")

    ydl_opts = {
        "outtmpl": outtmpl,
        "logger": SilentLogger(),
        "quiet": True,
        "no_warnings": True,

        # garante vídeo com áudio
        "format": _format_for_quality(quality if not to_mp3 else "mp3"),

        # não pega playlists
        "noplaylist": True,

        # força saída MP4 quando possível
        "merge_output_format": "mp4",

        # melhora compatibilidade
        "postprocessor_args": ["-movflags", "faststart"],

        # evita travamentos em vídeos HLS / DASH
        "hls_use_mpegts": True,
        "hls_prefer_native": False,
        "concurrent_fragment_downloads": 1,
        "fragment_retries": 20,
        "retries": 20,
    }

    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile

    # --- modo MP3 ---
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
        # --- conversão correta para MP4 ---
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4"   # <- correto (apenas 1 'r')
            },
            {"key": "FFmpegMetadata"},
        ]

    # Executa download
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        # caso seja playlist
        if "entries" in info and info["entries"]:
            info = info["entries"][0]

        filepath = ydl.prepare_filename(info)

        # ajuste caso MP3
        if (to_mp3 or quality == "mp3") and not filepath.lower().endswith(".mp3"):
            mp3 = os.path.splitext(filepath)[0] + ".mp3"
            if os.path.exists(mp3):
                filepath = mp3

        return filepath
