"""Shrink oversized non-YouTube media only when Telegram's bot limit requires it.

The source file is otherwise left untouched. If it exceeds MAX_FILE_MB we
re-encode at a calculated bitrate while preserving the exact frame dimensions
and sample aspect ratio: no crop, no stretch, no blur and no decorative bars.
"""

import json
import subprocess
from pathlib import Path

import jetbot_v2 as app

_ORIGINAL_DOWNLOAD_MEDIA = app.download_media


def _duration_seconds(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    value = json.loads(proc.stdout or "{}").get("format", {}).get("duration")
    return max(float(value or 0), 0.1)


def _fit_file(path: Path, max_mb: int) -> Path:
    limit_bytes = int(max_mb * 1024 * 1024)
    if path.stat().st_size <= limit_bytes:
        return path

    duration = _duration_seconds(path)
    # Leave headroom for container overhead and Telegram's hard cap.
    target_bytes = min(limit_bytes - 1_000_000, int(46 * 1024 * 1024))
    total_bps = max(int(target_bytes * 8 / duration * 0.94), 500_000)
    audio_bps = 128_000
    video_bps = max(total_bps - audio_bps, 350_000)

    output = path.with_name(path.stem + "-telegram.mp4")
    cmd = [
        "ffmpeg", "-y", "-i", str(path),
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast",
        "-b:v", str(video_bps), "-maxrate", str(int(video_bps * 1.12)),
        "-bufsize", str(int(video_bps * 2)),
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-map_metadata", "0",
        str(output),
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=240, check=True)

    if output.exists() and output.stat().st_size <= limit_bytes:
        print(
            f"[JetBot Media] Telegram fit source_mb={path.stat().st_size/1048576:.1f} "
            f"final_mb={output.stat().st_size/1048576:.1f} dimensions=preserved"
        )
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        return output

    # One conservative retry when mux/container overhead was higher than expected.
    retry = path.with_name(path.stem + "-telegram-small.mp4")
    retry_video_bps = max(int(video_bps * 0.78), 300_000)
    retry_cmd = cmd[:-1]
    retry_cmd[retry_cmd.index(str(video_bps))] = str(retry_video_bps)
    retry_cmd[retry_cmd.index(str(int(video_bps * 1.12)))] = str(int(retry_video_bps * 1.12))
    retry_cmd[retry_cmd.index(str(int(video_bps * 2)))] = str(int(retry_video_bps * 2))
    retry_cmd.append(str(retry))
    subprocess.run(retry_cmd, capture_output=True, text=True, timeout=240, check=True)
    if output.exists():
        output.unlink(missing_ok=True)
    if retry.exists() and retry.stat().st_size <= limit_bytes:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        print(
            f"[JetBot Media] Telegram fit retry final_mb={retry.stat().st_size/1048576:.1f} "
            "dimensions=preserved"
        )
        return retry
    raise RuntimeError("Não consegui reduzir o arquivo para o limite do Telegram sem alterar a proporção.")


def download_media_with_telegram_fit(url, uid):
    result = _ORIGINAL_DOWNLOAD_MEDIA(url, uid)
    if not isinstance(result, dict) or not result.get("path"):
        return result
    path = Path(result["path"])
    if path.exists() and path.stat().st_size > app.MAX_FILE_MB * 1024 * 1024:
        fitted = _fit_file(path, app.MAX_FILE_MB)
        result = dict(result)
        result["path"] = str(fitted)
        result["telegram_fitted"] = True
    return result


app.download_media = download_media_with_telegram_fit
print("[JetBot Media] Telegram size-fit patch loaded")
