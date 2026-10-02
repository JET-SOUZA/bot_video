import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

import telegram_fit_patch as patch


class TelegramFitPatchTests(unittest.TestCase):
    def test_transcode_timeout_scales_for_long_videos(self):
        self.assertEqual(patch._transcode_timeout_seconds(30), 900)
        self.assertEqual(patch._transcode_timeout_seconds(280), 1800)
        self.assertEqual(patch._transcode_timeout_seconds(3600), 3600)

    def test_ffmpeg_timeout_is_cleaned_up_and_hidden_from_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "partial.mp4"
            output.write_bytes(b"partial")
            with mock.patch.object(
                patch.subprocess,
                "run",
                side_effect=patch.subprocess.TimeoutExpired(["ffmpeg"], 900),
            ):
                with self.assertRaisesRegex(RuntimeError, "demorou além do limite"):
                    patch._run_ffmpeg(["ffmpeg"], output, 30, "test")
            self.assertFalse(output.exists())

    def test_twitter_is_normalized_before_telegram_size_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "twitter.mp4"
            source.write_bytes(b"source")
            normalized = Path(tmp) / "twitter-telegram-normalized.mp4"
            normalized.write_bytes(b"normalized")
            result = {"path": str(source), "platform": "twitter"}
            metadata = {
                     "width": 720, "height": 1280, "duration": 88,
                     "sample_aspect_ratio": "1:1", "display_aspect_ratio": "9:16",
                     "codec_name": "h264", "pix_fmt": "yuv420p",
            }
            progress = mock.Mock()
            with mock.patch.object(patch, "_ORIGINAL_DOWNLOAD_MEDIA", return_value=result), \
                 mock.patch.object(patch, "_remux_standard_twitter_video", return_value=normalized) as remux, \
                 mock.patch.object(patch, "_normalize_for_telegram") as normalize, \
                 mock.patch.object(patch, "_video_metadata", return_value=metadata):
                final = patch.download_media_with_telegram_fit(
                    "https://x.com/u/status/1", 1, progress
                )
        remux.assert_called_once_with(source)
        normalize.assert_not_called()
        progress.assert_called_once_with("⏳ Corrigindo a proporção para o Telegram...")
        self.assertTrue(final["telegram_normalized"])
        self.assertTrue(final["telegram_fast_remuxed"])
        self.assertTrue(final["path"].endswith("twitter-telegram-normalized.mp4"))
        self.assertEqual((final["width"], final["height"], final["duration"]), (720, 1280, 88))

    def test_handler_forwards_normalized_geometry(self):
        source = (Path(__file__).resolve().parents[1] / "jetbot_v2.py").read_text(encoding="utf-8")
        self.assertIn('for field in ("width", "height", "duration")', source)
        self.assertIn("**video_kwargs", source)

    def test_stale_geometry_from_downloader_is_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "twitter.mp4"
            source.write_bytes(b"source")
            normalized = Path(tmp) / "twitter-telegram-normalized.mp4"
            normalized.write_bytes(b"normalized")
            result = {
                "path": str(source),
                "platform": "twitter",
                "width": 1280,
                "height": 720,
            }
            with mock.patch.object(patch, "_ORIGINAL_DOWNLOAD_MEDIA", return_value=result), \
                 mock.patch.object(patch, "_remux_standard_twitter_video", return_value=normalized), \
                 mock.patch.object(patch, "_video_metadata", return_value={
                     "width": 480, "height": 852, "duration": 280,
                     "sample_aspect_ratio": "1:1", "display_aspect_ratio": "40:71",
                     "codec_name": "h264", "pix_fmt": "yuv420p",
                 }):
                final = patch.download_media_with_telegram_fit("https://x.com/u/status/2", 1)

        self.assertEqual((final["width"], final["height"], final["duration"]), (480, 852, 280))

    def test_nonstandard_twitter_video_uses_transcode_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "twitter.mp4"
            source.write_bytes(b"source")
            normalized = Path(tmp) / "twitter-telegram-normalized.mp4"
            normalized.write_bytes(b"normalized")
            metadata = {
                "width": 640, "height": 640, "duration": 30,
                "sample_aspect_ratio": "9:16", "display_aspect_ratio": "9:16",
                "codec_name": "h264", "pix_fmt": "yuv420p",
            }
            with mock.patch.object(
                patch, "_ORIGINAL_DOWNLOAD_MEDIA",
                return_value={"path": str(source), "platform": "twitter"},
            ), mock.patch.object(
                patch, "_video_metadata", return_value=metadata
            ), mock.patch.object(
                patch, "_normalize_for_telegram", return_value=normalized
            ) as normalize, mock.patch.object(
                patch, "_remux_standard_twitter_video"
            ) as remux:
                patch.download_media_with_telegram_fit("https://x.com/u/status/3", 1)

        normalize.assert_called_once_with(source)
        remux.assert_not_called()


if __name__ == "__main__":
    unittest.main()
