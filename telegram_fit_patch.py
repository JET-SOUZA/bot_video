"""Prepare non-YouTube media for Telegram without changing its display ratio.

X/Twitter media is converted to a conservative Telegram/iOS MP4 profile so the
display ratio is baked into square pixels instead of depending on container
metadata. Other oversized media is re-encoded only when MAX_FILE_MB requires
it. There is no crop, stretch, blur or decorative padding.
"""

import json
import subprocess
from pathlib import Path

import jetbot_v2 as app

_ORIGINAL_DOWNLOAD_MEDIA = app.download_media


def _normalize_for_telegram(path: Path) -> Path:
    """Bake the source display ratio into a standard Telegram/iOS MP4.

    A stream-copy remux is not enough for every X rendition: Telegram can cache
    or misread its pixel-aspect/rotation metadata and show a portrait frame as
    a square. Re-encoding makes the displayed geometry unambiguous: H.264,
    yuv420p, square pixels, no rotation tag and even frame dimensions.
    """
    output = path.with_name(path.stem + "-telegram-normalized.mp4")
    cmd = [
        "ffmpeg", "-y", "-i", str(path),
        "-map", "0:v:0", "-map", "0:a?",
        "-vf", (
            "scale='trunc(iw*sar/2)*2':'trunc(ih/2)*2',setsar=1,"
            "scale='min(1280,iw)':'min(1280,ih)':"
            "force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1"
        ),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-tag:v", "avc1",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", "-avoid_negative_ts", "make_zero",
        "-map_metadata", "-1", "-metadata:s:v:0", "rotate=0",
        str(output),
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=480, check=True)
    if not output.exists() or output.stat().st_size <= 0:
        raise RuntimeError("O vídeo do X/Twitter não pôde ser normalizado para o Telegram.")
    path.unlink(missing_ok=True)
    print("[JetBot Media] X/Twitter normalized to H.264/yuv420p with square pixels")
    return output


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


def _video_metadata(path: Path) -> dict:
    """Return safe sendVideo metadata from the normalized square-pixel MP4."""
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", (
                "stream=width,height,sample_aspect_ratio,display_aspect_ratio,"
                "codec_name,pix_fmt:stream_side_data=rotation:format=duration"
            ),
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    payload = json.loads(proc.stdout or "{}")
    stream = (payload.get("streams") or [{}])[0]
    fmt = payload.get("format") or {}
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    duration = max(int(round(float(fmt.get("duration") or 0))), 1)
    if width <= 0 or height <= 0:
        raise RuntimeError("Não foi possível identificar a proporção do vídeo final.")
    sample_aspect_ratio = stream.get("sample_aspect_ratio") or "1:1"
    if sample_aspect_ratio not in {"1:1", "N/A"}:
        raise RuntimeError("O vídeo final ainda possui pixels não quadrados.")
    return {
        "width": width,
        "height": height,
        "duration": duration,
        "sample_aspect_ratio": sample_aspect_ratio,
        "display_aspect_ratio": stream.get("display_aspect_ratio") or "",
        "codec_name": stream.get("codec_name") or "",
        "pix_fmt": stream.get("pix_fmt") or "",
    }


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
        "-vf", (
            "scale='min(1280,iw)':'min(1280,ih)':"
            "force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1"
        ),
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
    result = dict(result)
    if result.get("platform") == "twitter" and path.exists():
        path = _normalize_for_telegram(path)
        result["path"] = str(path)
        result["telegram_normalized"] = True
    if path.exists() and path.stat().st_size > app.MAX_FILE_MB * 1024 * 1024:
        fitted = _fit_file(path, app.MAX_FILE_MB)
        result["path"] = str(fitted)
        result["telegram_fitted"] = True
        path = fitted
    if path.exists() and result.get("platform") == "twitter":
        metadata = _video_metadata(path)
        # This file has square pixels and no rotation metadata, so its encoded
        # dimensions are now the exact display dimensions Telegram must use.
        result.update({field: metadata[field] for field in ("width", "height", "duration")})
        print(
            f"[JetBot Media] Telegram geometry width={metadata['width']} "
            f"height={metadata['height']} duration={metadata['duration']} "
            f"sar={metadata['sample_aspect_ratio']} dar={metadata['display_aspect_ratio']} "
            f"codec={metadata['codec_name']} pix_fmt={metadata['pix_fmt']}"
        )
    return result


app.download_media = download_media_with_telegram_fit
print("[JetBot Media] Telegram size-fit patch loaded")
