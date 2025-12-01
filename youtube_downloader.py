# youtube_downloader.py
import os
import shutil
from pathlib import Path
from datetime import datetime

# Tenta usar módulo Python
try:
    import yt_dlp as ytdlp_module
    _HAS_YT_DLP_MODULE = True
except Exception:
    _HAS_YT_DLP_MODULE = False

import subprocess


SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOAD_DIR = SCRIPT_DIR / "downloads" / "youtube"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _check_executable(name):
    return shutil.which(name)


def _ensure_ffmpeg_available():
    ff = _check_executable("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg não encontrado no PATH (Render).")


# -----------------------------
# FORMATOS PARA QUALIDADES
# -----------------------------
def get_format_for_quality(quality: str, to_mp3: bool):
    if to_mp3:
        return "bestaudio/best"

    table = {
        "144": "bv*[height<=144]+ba/best",
        "240": "bv*[height<=240]+ba/best",
        "360": "bv*[height<=360]+ba/best",
        "480": "bv*[height<=480]+ba/best",
        "720": "bv*[height<=720]+ba/best",
        "1080": "bv*[height<=1080]+ba/best",
        "1440": "bv*[height<=1440]+ba/best",
        "2160": "bv*[height<=2160]+ba/best",
    }
    return table.get(str(quality), "bv*+ba/best")


def _find_final_file(basename_prefix: str):
    files = sorted(DOWNLOAD_DIR.glob(f"{basename_prefix}*"), key=os.path.getmtime)
    return str(files[-1]) if files else None


# ----------------------------------------------------------
#      NOVO DOWNLOAD — MAIS RÁPIDO, SEM TRAVAR
# ----------------------------------------------------------
def download_youtube_file(url: str, quality="480", to_mp3=False, cookiefile=None, timeout=120):
    _ensure_ffmpeg_available()

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    basename = f"video-{timestamp}"
    outtmpl = str(DOWNLOAD_DIR / f"{basename}.%(ext)s")

    # -----------------------------------------------
    #   OPÇÕES OTIMIZADAS (MUITO MAIS RÁPIDAS)
    # -----------------------------------------------
    ytdl_opts = {
        "outtmpl": outtmpl,
        "format": get_format_for_quality(quality, to_mp3),
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,

        # 🔥 Fast download
        "concurrent_fragment_downloads": 10,
        "retries": 5,
        "fragment_retries": 5,
        "skip_unavailable_fragments": True,

        # 🔥 Timeout anti-trava
        "socket_timeout": 15,
        "extractor_args": {"youtube": {"player_client": ["web"]}},

        # 🔥 Evita travamentos do HLS da Google
        "hls_use_mpegts": False,

        "merge_output_format": "mp4",
        "postprocessor_args": ["-movflags", "faststart"],
    }

    if cookiefile:
        ytdl_opts["cookiefile"] = cookiefile

    if to_mp3:
        ytdl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]

    # -----------------------------------------------
    # 1) Preferir módulo Python yt_dlp
    # -----------------------------------------------
    if _HAS_YT_DLP_MODULE:
        try:
            with ytdlp_module.YoutubeDL(ytdl_opts) as ydl:
                ydl.download([url])

            final = _find_final_file(basename)
            if final:
                return final
            raise FileNotFoundError("Arquivo final não encontrado via módulo yt_dlp.")
        except Exception as e:
            raise Exception(f"[yt_dlp module error] {e}")

    # -----------------------------------------------
    # 2) Fallback: usar binário yt-dlp
    # -----------------------------------------------
    binary = _check_executable("yt-dlp")
    if not binary:
        raise RuntimeError("yt-dlp não encontrado no ambiente. Instale o binário ou use o módulo Python.")

    cmd = [
        binary,
        "-o", outtmpl,
        "-f", get_format_for_quality(quality, to_mp3),
        "--no-playlist",
        "--abort-on-error",
        "--concurrent-fragments", "10",
        "--retries", "5",
        "--fragment-retries", "5",
        "--skip-unavailable-fragments",
        "--socket-timeout", "15",
        "--merge-output-format", "mp4",
        "--postprocessor-args", "-movflags faststart",
    ]

    if cookiefile:
        cmd += ["--cookies", cookiefile]

    if to_mp3:
        cmd += ["--extract-audio", "--audio-format", "mp3", "--audio-quality", "192K"]

    cmd.append(url)

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if proc.returncode != 0:
        raise Exception(f"[yt-dlp binary error]\n{proc.stderr[-1500:]}")

    final = _find_final_file(basename)
    if final:
        return final

    raise FileNotFoundError("Arquivo final não encontrado (via yt-dlp).")
