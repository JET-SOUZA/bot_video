import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

import telegram_fit_patch


def _probe(path: Path):
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    data = json.loads(proc.stdout or "{}")
    video = next(stream for stream in data["streams"] if stream.get("codec_type") == "video")
    audio = [stream for stream in data["streams"] if stream.get("codec_type") == "audio"]
    return video, audio


def _make_fixture(path: Path, width: int, height: int):
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size={width}x{height}:rate=24",
            "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=44100",
            "-t", "1.5", "-shortest",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "0",
            "-c:a", "aac", "-b:a", "128k", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )


def _ensure_size(path: Path, minimum_bytes: int):
    # Trailing bytes do not alter the decodable MP4 streams, but let the test
    # exercise exactly the size gate used by Telegram without a huge fixture.
    if path.stat().st_size < minimum_bytes:
        with path.open("ab") as fh:
            fh.truncate(minimum_bytes)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe unavailable")
class RealMediaFidelityTests(unittest.TestCase):
    def test_oversized_video_preserves_geometry_and_audio_for_common_ratios(self):
        cases = [(360, 640), (480, 480), (640, 360)]  # 9:16, 1:1, 16:9
        for width, height in cases:
            with self.subTest(width=width, height=height), tempfile.TemporaryDirectory() as td:
                source = Path(td) / "source.mp4"
                _make_fixture(source, width, height)
                _ensure_size(source, 1_300_000)
                before_video, before_audio = _probe(source)
                self.assertTrue(before_audio)
                self.assertGreater(source.stat().st_size, 1024 * 1024)

                output = telegram_fit_patch._fit_file(source, 1)
                after_video, after_audio = _probe(output)

                self.assertLessEqual(output.stat().st_size, 1024 * 1024)
                self.assertEqual((before_video["width"], before_video["height"]), (width, height))
                self.assertEqual((after_video["width"], after_video["height"]), (width, height))
                self.assertTrue(after_audio, "audio stream must survive Telegram fitting")

    def test_real_49mb_gate_preserves_portrait_geometry_and_audio(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "portrait.mp4"
            _make_fixture(source, 360, 640)
            _ensure_size(source, 50 * 1024 * 1024)
            before_video, before_audio = _probe(source)
            self.assertTrue(before_audio)
            self.assertGreater(source.stat().st_size, 49 * 1024 * 1024)

            output = telegram_fit_patch._fit_file(source, 49)
            after_video, after_audio = _probe(output)

            self.assertLessEqual(output.stat().st_size, 49 * 1024 * 1024)
            self.assertEqual((before_video["width"], before_video["height"]), (360, 640))
            self.assertEqual((after_video["width"], after_video["height"]), (360, 640))
            self.assertTrue(after_audio)


if __name__ == "__main__":
    unittest.main()
