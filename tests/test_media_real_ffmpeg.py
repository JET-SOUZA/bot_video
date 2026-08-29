import json
import os
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
    # Make the container definitely exceed the 1 MB test threshold while
    # keeping a decodable MP4. ffmpeg ignores harmless trailing bytes.
    minimum = 1_300_000
    if path.stat().st_size < minimum:
        with path.open("ab") as fh:
            fh.write(b"\0" * (minimum - path.stat().st_size))


class RealMediaFidelityTests(unittest.TestCase):
    def test_oversized_video_preserves_geometry_and_audio_for_common_ratios(self):
        cases = [(360, 640), (480, 480), (640, 360)]  # 9:16, 1:1, 16:9
        for width, height in cases:
            with self.subTest(width=width, height=height), tempfile.TemporaryDirectory() as td:
                source = Path(td) / "source.mp4"
                _make_fixture(source, width, height)
                before_video, before_audio = _probe(source)
                self.assertTrue(before_audio)
                self.assertGreater(source.stat().st_size, 1024 * 1024)

                output = telegram_fit_patch._fit_file(source, 1)
                after_video, after_audio = _probe(output)

                self.assertLessEqual(output.stat().st_size, 1024 * 1024)
                self.assertEqual((before_video["width"], before_video["height"]), (width, height))
                self.assertEqual((after_video["width"], after_video["height"]), (width, height))
                self.assertTrue(after_audio, "audio stream must survive Telegram fitting")


if __name__ == "__main__":
    unittest.main()
