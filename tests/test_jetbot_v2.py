import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

import jetbot_v2 as bot


class FunctionalParityTests(unittest.TestCase):
    def test_existing_features_are_sourced_from_main(self):
        self.assertIs(bot.is_premium, bot.legacy.is_premium)
        self.assertIs(bot.verificar_limite, bot.legacy.verificar_limite)
        self.assertIs(bot.verificar_limite_youtube, bot.legacy.verificar_limite_youtube)
        self.assertEqual(bot.YT_FREE_LIMIT, bot.legacy.YT_FREE_LIMIT)
        self.assertEqual(bot.YT_FREE_LIMIT, 3)

    def test_free_youtube_keyboard_keeps_mp3_and_locks(self):
        keyboard = bot._build_yt_keyboard("tok", False, 2).inline_keyboard
        self.assertEqual([b.text for b in keyboard[0]], ["360p", "480p", "MP3"])
        self.assertTrue(all(b.callback_data == "yt_locked" for b in keyboard[1]))
        self.assertEqual(keyboard[2][0].callback_data, "yt_locked")
        self.assertIn("2/3", keyboard[3][0].text)

    def test_premium_youtube_keyboard_unlocks_all_qualities(self):
        keyboard = bot._build_yt_keyboard("tok", True, 0).inline_keyboard
        callbacks = [button.callback_data for row in keyboard[:3] for button in row]
        for quality in ("720", "1080", "1440", "2160"):
            self.assertIn(f"yt_start:tok:{quality}", callbacks)
        self.assertIn("ilimitados", keyboard[3][0].text)


class PlatformDetectionTests(unittest.TestCase):
    def test_supported_platforms(self):
        cases = {
            "https://www.instagram.com/reel/abc/": "instagram",
            "https://vm.tiktok.com/ZMabc/": "tiktok",
            "https://x.com/user/status/123": "twitter",
            "https://youtube.com/shorts/abc": "youtube",
            "https://youtu.be/abc": "youtube",
            "https://br.shp.ee/abc": "shopee",
            "https://www.pinterest.com/pin/123/": "pinterest",
            "https://pin.it/abc": "pinterest",
            "https://www.facebook.com/reel/123": "facebook",
            "https://fb.watch/abc/": "facebook",
            "https://www.reddit.com/r/test/comments/abc": "reddit",
            "https://redd.it/abc": "reddit",
            "https://vimeo.com/123": "vimeo",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(bot.detect_platform(url), expected)


class YoutubeMotorTests(unittest.TestCase):
    def test_video_options_respect_selected_quality(self):
        opts = bot.build_youtube_ydl_options(Path("/tmp"), "test", "1080", False)
        self.assertIn("height<=1080", opts["format"])
        self.assertEqual(opts["merge_output_format"], "mp4")

    def test_mp3_options_use_ffmpeg(self):
        opts = bot.build_youtube_ydl_options(Path("/tmp"), "test", "360", True)
        self.assertEqual(opts["format"], "bestaudio/best")
        self.assertEqual(opts["postprocessors"][0]["key"], "FFmpegExtractAudio")
        self.assertEqual(opts["postprocessors"][0]["preferredcodec"], "mp3")


class FakeYDL:
    last_opts = None

    def __init__(self, opts):
        type(self).last_opts = opts
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def extract_info(self, url, download=True):
        directory = Path(self.opts["outtmpl"]).parent
        directory.mkdir(parents=True, exist_ok=True)
        prefix = Path(self.opts["outtmpl"]).name.split("-%(id)s")[0]
        suffix = ".mp3" if self.opts.get("format") == "bestaudio/best" else ".mp4"
        (directory / f"{prefix}-mock{suffix}").write_bytes(b"mock-data")
        return {"title": "Mock", "id": "mock", "ext": suffix.lstrip(".")}


class DownloadMockTests(unittest.TestCase):
    def test_general_download_flow_with_mock_ytdlp(self):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(bot, "DOWNLOADS_DIR", Path(td)), \
             mock.patch.object(bot.yt_dlp, "YoutubeDL", FakeYDL):
            result = bot.download_media("https://www.instagram.com/reel/abc/", 42)
            try:
                self.assertEqual(result["platform"], "instagram")
                self.assertTrue(Path(result["path"]).exists())
            finally:
                shutil.rmtree(result["temp_dir"], ignore_errors=True)

    def test_youtube_blocking_engine_returns_mp3(self):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(bot, "DOWNLOAD_DIR", Path(td)), \
             mock.patch.object(bot.yt_dlp, "YoutubeDL", FakeYDL):
            path = bot.download_youtube_file_v2("https://youtu.be/abc", quality="mp3", to_mp3=True)
            try:
                self.assertEqual(Path(path).suffix, ".mp3")
                self.assertEqual(FakeYDL.last_opts["postprocessors"][0]["key"], "FFmpegExtractAudio")
            finally:
                Path(path).unlink(missing_ok=True)


class StartupAndDockerTests(unittest.TestCase):
    def test_application_builds_without_network(self):
        app = bot.build_application()
        self.assertIsNotNone(app)
        handler_count = sum(len(group) for group in app.handlers.values())
        self.assertGreaterEqual(handler_count, 8)

    def test_docker_runtime(self):
        root = Path(__file__).resolve().parents[1]
        docker = (root / "Dockerfile").read_text(encoding="utf-8")
        requirements = (root / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("ffmpeg", docker)
        self.assertIn("node:20", docker)
        self.assertIn("bgutil-ytdlp-pot-provider", docker)
        self.assertIn("bgutil-ytdlp-pot-provider", requirements)
        self.assertIn('CMD ["python", "jetbot_v2.py"]', docker)


if __name__ == "__main__":
    unittest.main()
