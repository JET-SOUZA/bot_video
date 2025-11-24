# youtube_downloader.py
import os
import shutil
import glob
from pathlib import Path
from datetime import datetime

# Prefer using the Python API (yt_dlp). If not available, will fallback to subprocess call.
try:
    import yt_dlp as ytdlp_module
    _HAS_YT_DLP_MODULE = True
except Exception:
    _HAS_YT_DLP_MODULE = False

import subprocess
import sys

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOAD_DIR = SCRIPT_DIR / "downloads" / "youtube"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

def _check_executable(name):
    """Return path to executable or None."""
    return shutil.which(name)

def _ensure_ffmpeg_available():
    ff = _check_executable("ffmpeg")
    if not ff:
        # give a clear error so logs show exactly what's missing
        raise RuntimeError("ffmpeg não encontrado no PATH. Instale ffmpeg no ambiente (Render) ou inclua um binário).")

def get_format_for_quality(quality: str, to_mp3: bool):
    """Sempre retorna streams separados + áudio."""
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

def download_youtube_file(url: str, quality="480", to_mp3=False, cookiefile=None, timeout=None):
    """
    Download using yt_dlp Python module when available, otherwise fallback
    to calling 'yt-dlp' binary. Returns final filepath.
    Raises Exception on failure with helpful message.
    """
    _ensure_ffmpeg_available()

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    basename = f"video-{timestamp}"
    if to_mp3:
        outtmpl = str(DOWNLOAD_DIR / f"{basename}.%(ext)s")
    else:
        outtmpl = str(DOWNLOAD_DIR / f"{basename}.%(ext)s")

    ytdl_opts = {
        "outtmpl": outtmpl,
        "format": get_format_for_quality(quality, to_mp3),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 20,
        "fragment_retries": 20,
        "hls_use_mpegts": True,
        "merge_output_format": "mp4",
        "postprocessor_args": ["-movflags", "faststart"],
    }

    if cookiefile:
        ytdl_opts["cookiefile"] = cookiefile

    if to_mp3:
        # configure extraction
        ytdl_opts.update({
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        })

    # Prefer Python module (no external binary dependency)
    if _HAS_YT_DLP_MODULE:
        try:
            with ytdlp_module.YoutubeDL(ytdl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # ydl may produce several files; try to deduce final file
                # If extracting audio, try to get filename from info
                possible = []
                if info:
                    # info dict may contain 'requested_downloads' or 'requested_formats'
                    # But easiest: search downloads dir for our basename prefix
                    possible.append(_find_final_file(basename))
                # fallback search
                final = next((p for p in possible if p), None)
                if final and os.path.exists(final):
                    return final
                # fallback: glob
                final = _find_final_file(basename)
                if final:
                    return final
                raise FileNotFoundError("Arquivo final não encontrado após download (via yt_dlp module).")
        except Exception as e:
            raise Exception(f"[yt_dlp module error] {e}")
    else:
        # Fallback to calling yt-dlp binary
        binary = _check_executable("yt-dlp")
        if not binary:
            raise RuntimeError("Nem o módulo Python yt_dlp nem o binário 'yt-dlp' foram encontrados. Instale um deles.")
        cmd = [
            binary,
            "-o", outtmpl,
            "-f", get_format_for_quality(quality, to_mp3),
            "--no-warnings",
            "--restrict-filenames",
            "--no-playlist",
            "--retries", "20",
            "--fragment-retries", "20",
            "--hls-use-mpegts",
            "--merge-output-format", "mp4",
            "--postprocessor-args", "-movflags faststart",
        ]
        if cookiefile:
            cmd += ["--cookies", cookiefile]
        if to_mp3:
            cmd += ["--extract-audio", "--audio-format", "mp3", "--audio-quality", "192K"]
        cmd.append(url)

        # run and capture output
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            # show part of stderr to logs
            tail = proc.stderr[-2000:] if proc.stderr else proc.stdout[-2000:]
            raise Exception(f"[yt-dlp binary error] returncode={proc.returncode}\n{tail}")
        # find final file
        final = _find_final_file(basename)
        if final and os.path.exists(final):
            return final
        else:
            raise FileNotFoundError("Arquivo final não encontrado após download (via yt-dlp binary).")
