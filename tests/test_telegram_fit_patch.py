import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

import telegram_fit_patch as patch


class TelegramFitPatchTests(unittest.TestCase):
    def test_twitter_is_remuxed_before_telegram_size_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "twitter.mp4"
            source.write_bytes(b"source")
            remuxed = Path(tmp) / "twitter-telegram-remux.mp4"
            remuxed.write_bytes(b"remuxed")
            result = {"path": str(source), "platform": "twitter"}
            with mock.patch.object(patch, "_ORIGINAL_DOWNLOAD_MEDIA", return_value=result), \
                 mock.patch.object(patch, "_remux_for_telegram", return_value=remuxed) as remux, \
                 mock.patch.object(patch, "_video_metadata", return_value={"width": 720, "height": 1280, "duration": 88}):
                final = patch.download_media_with_telegram_fit("https://x.com/u/status/1", 1)
        remux.assert_called_once_with(source)
        self.assertTrue(final["telegram_remuxed"])
        self.assertTrue(final["path"].endswith("twitter-telegram-remux.mp4"))
        self.assertEqual((final["width"], final["height"], final["duration"]), (720, 1280, 88))

    def test_handler_forwards_exact_video_metadata_to_telegram(self):
        source = (Path(__file__).resolve().parents[1] / "jetbot_v2.py").read_text(encoding="utf-8")
        self.assertIn('for field in ("width", "height", "duration")', source)
        self.assertIn("**video_kwargs", source)


if __name__ == "__main__":
    unittest.main()
