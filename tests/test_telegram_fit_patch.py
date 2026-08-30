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
                 mock.patch.object(patch, "_remux_for_telegram", return_value=remuxed) as remux:
                final = patch.download_media_with_telegram_fit("https://x.com/u/status/1", 1)
        remux.assert_called_once_with(source)
        self.assertTrue(final["telegram_remuxed"])
        self.assertTrue(final["path"].endswith("twitter-telegram-remux.mp4"))


if __name__ == "__main__":
    unittest.main()
