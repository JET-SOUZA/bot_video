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
        # fallback universal seguro
        return "bv*+ba/b"

    # formato correto e estável
    return f"bv*[height<={h}]+ba/b"


def download_youtube_file(url: str, quality: str = "480", to_mp3: bool = False, cookiefile: str = None):
    """
    Faz o download (bloqueante). Retorna caminho absoluto do arquivo final.
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

        # força MP4 quando possível (não quebra webm)
        "merge_output_format": "mp4",

        # melhora compatibilidade com players
        "postprocessor_args": ["-movflags", "faststart"],
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
        # converte vídeo para MP4 corretamente
      ydl_opts["postprocessors"] = [
    {
        "key": "FFmpegVideoConvertor",
        "preferedformat": "mp4"   # <- correto (com 1 'r')
    },
    {"key": "FFmpegMetadata"}
]


    # Executa download
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        if "entries" in info and info["entries"]:
            info = info["entries"][0]

        filepath = ydl.prepare_filename(info)

        # Corrige saída MP3
        if (to_mp3 or quality == "mp3") and not filepath.lower().endswith(".mp3"):
            mp3 = os.path.splitext(filepath)[0] + ".mp3"
            if os.path.exists(mp3):
                filepath = mp3

        return filepath
