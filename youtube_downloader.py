import os
import yt_dlp
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOAD_DIR = SCRIPT_DIR / "downloads" / "youtube"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


class SilentLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): print(msg)


def get_format_for_quality(quality: str):
    """Retorna a expressão correta do yt-dlp para a qualidade escolhida."""

    if quality == "mp3":
        return "bestaudio/best"

    table = {
        "360":  "bestvideo[height<=360]+bestaudio/best",
        "480":  "bestvideo[height<=480]+bestaudio/best",
        "720":  "bestvideo[height<=720]+bestaudio/best",
        "1080": "bestvideo[height<=1080]+bestaudio/best",
        "1440": "bestvideo[height<=1440]+bestaudio/best",
        "2160": "bestvideo[height<=2160]+bestaudio/best",
    }

    return table.get(str(quality), "bestvideo+bestaudio/best")


def download_youtube_file(url: str, quality: str = "480", to_mp3: bool = False, cookiefile: str = None):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_title = "%(title)s"
    outtmpl = str(DOWNLOAD_DIR / f"{safe_title}-{timestamp}.%(ext)s")

    ydl_opts = {
        "outtmpl": outtmpl,
        "logger": SilentLogger(),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,

        # formato correto baseado na qualidade
        "format": get_format_for_quality("mp3" if to_mp3 else quality),

        # saída final preferida como mp4
        "merge_output_format": "mp4",

        # melhora compatibilidade
        "postprocessor_args": ["-movflags", "faststart"],

        # estabilidade do download
        "hls_use_mpegts": True,
        "hls_prefer_native": False,
        "fragment_retries": 20,
        "retries": 20,
    }

    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile

    # --- modo MP3 ---
    if to_mp3 or quality == "mp3":
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                },
                {"key": "FFmpegMetadata"},
            ]
        })
    else:
        # somente metadados; conversão para mp4 é automática via merge_output_format
        ydl_opts["postprocessors"] = [
            {"key": "FFmpegMetadata"},
        ]

    # --- EXECUTA O DOWNLOAD ---
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        if "entries" in info and info["entries"]:
            info = info["entries"][0]

        filepath = ydl.prepare_filename(info)

        # caso tenha virado mp3
        if (to_mp3 or quality == "mp3") and not filepath.lower().endswith(".mp3"):
            mp3_path = os.path.splitext(filepath)[0] + ".mp3"
            if os.path.exists(mp3_path):
                filepath = mp3_path

        return filepath
