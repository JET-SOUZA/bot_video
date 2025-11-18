# youtube_downloader.py
#
# Suporta TUDO: 360p, 480p, 720p, 1080p, 1440p (2K), 2160p (4K)
# sem estourar a memória do Render
# baixa vídeo e áudio SEPARADOS para qualidades altas
# mp3 continua leve
#

import os
import yt_dlp
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOAD_DIR = SCRIPT_DIR / "downloads" / "youtube"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


def build_format(quality):
    """
    Para qualidades acima de 480p, usamos vídeo + áudio separados.
    Para 360/480, enviamos mp4 junto (light).
    """

    if quality == "mp3":
        return "bestaudio/best"

    try:
        h = int(quality)
    except:
        h = 480

    # Até 480p → MP4 leve
    if h <= 480:
        return f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/best[ext=mp4]/mp4"

    # Acima de 720p → streams separados (DASH)
    return f"bv*[height={h}]/bv*[height<={h}]/bestvideo + ba/bestaudio"


def download_youtube_file(url: str, quality: str = "480", to_mp3: bool = False, cookiefile: str = None):
    """
    Retorna o caminho do arquivo final.
    Para >480p retorna DOIS arquivos:
        (video_path, audio_path)
    """

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    base = str(DOWNLOAD_DIR / f"%(title)s-{quality}p-{timestamp}")

    ydl_opts = {
        "outtmpl": base + ".%(ext)s",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile

    # MP3 (leve)
    if to_mp3 or quality == "mp3":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}
        ]
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file = ydl.prepare_filename(info)
            file_mp3 = os.path.splitext(file)[0] + ".mp3"
            return file_mp3

    # Formato de vídeo
    ydl_opts["format"] = build_format(quality)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        if "entries" in info:
            info = info["entries"][0]

        # identificar os arquivos baixados
        video = audio = None

        # yt-dlp salva com sufixos -video, -audio
        base_title = f"{info['title']}-{quality}p-{timestamp}"

        # procurar arquivos possíveis
        for f in os.listdir(DOWNLOAD_DIR):
            if base_title in f:
                if "video" in f:
                    video = str(DOWNLOAD_DIR / f)
                elif "audio" in f:
                    audio = str(DOWNLOAD_DIR / f)
                else:
                    # vídeos até 480p vêm juntos
                    video = str(DOWNLOAD_DIR / f)

        if quality in ["360", "480"]:
            return video  # único arquivo

        return video, audio
