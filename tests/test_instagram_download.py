import base64
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
import jetbot_v2 as bot


class InstagramDownloadTests(unittest.TestCase):
    def setUp(self):
        self.old_retry_at = bot._INSTAGRAM_RETRY_AT
        bot._INSTAGRAM_RETRY_AT = 0
        self.env = mock.patch.dict(os.environ, {}, clear=True)
        self.env.start()

    def tearDown(self):
        bot._INSTAGRAM_RETRY_AT = self.old_retry_at
        self.env.stop()

    def test_429_stops_fallback_and_next_request_without_network(self):
        error = bot.yt_dlp.utils.DownloadError("HTTP Error 429: Too Many Requests")
        with tempfile.TemporaryDirectory() as td, mock.patch.object(bot, "DOWNLOADS_DIR", Path(td)), mock.patch.object(bot.yt_dlp, "YoutubeDL") as ydl, mock.patch.object(bot.legacy, "extrair_video_instagram") as legacy:
            ydl.return_value.__enter__.return_value.extract_info.side_effect = error
            with self.assertRaisesRegex(bot.InstagramDownloadError, "429"):
                bot.download_media("https://www.instagram.com/reel/abc/", 42)
            with self.assertRaisesRegex(bot.InstagramDownloadError, "Aguarde cerca"):
                bot.download_media("https://www.instagram.com/reel/def/", 43)
            self.assertEqual(ydl.call_count, 1)
            legacy.assert_not_called()
            self.assertEqual(list(Path(td).iterdir()), [])

    def test_download_resumes_after_cooldown(self):
        bot._INSTAGRAM_RETRY_AT = 100
        with mock.patch.object(bot.time, "monotonic", return_value=101), mock.patch.object(bot, "_download_media", return_value={"ok": True}):
            self.assertEqual(bot.download_media("https://instagram.com/reel/a/", 1), {"ok": True})

    def test_story_without_session_does_not_contact_instagram(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(bot, "DOWNLOADS_DIR", Path(td)), mock.patch.object(bot.yt_dlp, "YoutubeDL") as ydl:
            with self.assertRaisesRegex(bot.InstagramDownloadError, "sessão válida"):
                bot.download_media("https://www.instagram.com/stories/user/123/", 1)
            ydl.assert_not_called()
            self.assertEqual(list(Path(td).iterdir()), [])

    def test_authenticated_story_keeps_cookies_and_downloads_once(self):
        cookies = "# Netscape HTTP Cookie File\n.instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\tfake-test-only\n"
        os.environ["COOKIES_IG_B64"] = base64.b64encode(cookies.encode()).decode()
        with tempfile.TemporaryDirectory() as td, mock.patch.object(bot, "DOWNLOADS_DIR", Path(td)), mock.patch.object(bot.yt_dlp, "YoutubeDL") as ydl:
            cookiepaths = []
            def extract(url, download=True):
                opts = ydl.call_args.args[0]
                cookiepaths.append(opts["cookiefile"])
                self.assertEqual(Path(opts["cookiefile"]).read_text(), cookies)
                self.assertEqual(opts["extractor_retries"], 0)
                (Path(opts["outtmpl"]).parent / "story.mp4").write_bytes(b"test")
                return {"title": "Story"}
            ydl.return_value.__enter__.return_value.extract_info.side_effect = extract
            result = bot.download_media("https://www.instagram.com/stories/user/123/", 1)
            self.assertTrue(Path(result["path"]).exists())
            self.assertFalse(Path(cookiepaths[0]).exists())
            self.assertEqual(ydl.call_count, 1)
            shutil.rmtree(result["temp_dir"])

    def test_expired_or_foreign_session_is_rejected(self):
        for domain, expiry in (("instagram.com", "1"), ("example.com", "0")):
            with tempfile.NamedTemporaryFile(mode="w") as f:
                f.write(f"# Netscape HTTP Cookie File\n.{domain}\tTRUE\t/\tTRUE\t{expiry}\tsessionid\ttest\n")
                f.flush()
                self.assertFalse(bot._instagram_has_session(f.name))

    def test_parallel_instagram_download_does_not_start_second_request(self):
        with bot._INSTAGRAM_LOCK, mock.patch.object(bot, "_download_media") as download:
            with self.assertRaisesRegex(bot.InstagramDownloadError, "em andamento"):
                bot.download_media("https://instagram.com/reel/a/", 1)
            download.assert_not_called()

    def test_instagram_pause_does_not_block_other_platforms(self):
        bot._INSTAGRAM_RETRY_AT = float("inf")
        with mock.patch.object(bot, "_download_media", return_value={"platform": "twitter"}):
            self.assertEqual(bot.download_media("https://x.com/u/status/1", 1)["platform"], "twitter")


if __name__ == "__main__":
    unittest.main()
