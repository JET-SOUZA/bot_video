import importlib.util
import os
import unittest
from pathlib import Path
from unittest import mock


_SPEC = importlib.util.spec_from_file_location("jetbot_sitecustomize_test", Path(__file__).resolve().parents[1] / "sitecustomize.py")
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)

os.environ.setdefault("TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
import youtube_auth_patch as auth


class YouTubeCookieStrategyTests(unittest.TestCase):
    def test_cookie_auth_uses_upstream_recommended_clients_first(self):
        base = {"cookiefile": "/tmp/youtube.cookies.txt"}
        initial = mod._initial_strategy(base)
        clients = initial["extractor_args"]["youtube"]["player_client"]
        self.assertEqual(clients, ["default", "web_embedded"])

    def test_authenticated_chain_avoids_cookie_incompatible_clients(self):
        chain = mod._strategy_chain({"cookiefile": "/tmp/youtube.cookies.txt"})
        labels = [label for label, _ in chain]
        joined = " ".join(labels)
        self.assertIn("auth-default-web-embedded", labels)
        self.assertIn("auth-any-available", labels)
        self.assertNotIn("mweb", joined)
        self.assertNotIn("android-vr", joined)
        self.assertNotIn("tv", joined)

    def test_final_authenticated_retry_relaxes_unavailable_video_format(self):
        base = {
            "cookiefile": "/tmp/youtube.cookies.txt",
            "format": "bv*[height<=360]+ba/b[height<=360]/b",
            "format_sort": ["res:360"],
        }
        chain = dict(mod._strategy_chain(base))
        final = chain["auth-any-available"]
        self.assertEqual(final["format"], "best/bestvideo*+bestaudio/bestvideo+bestaudio")
        self.assertNotIn("format_sort", final)

    def test_audio_retry_keeps_audio_only_selector(self):
        relaxed = mod._with_any_available_format({"format": "bestaudio/best"})
        self.assertEqual(relaxed["format"], "bestaudio/best")

    def test_player_response_failure_is_retryable(self):
        self.assertTrue(mod._retryable_youtube_error(RuntimeError("Failed to extract any player response")))

    def test_antibot_error_without_cookies_is_actionable_and_sanitized(self):
        raw = "ERROR: [youtube] secret-id: Sign in to confirm you're not a bot. Use --cookies"
        with mock.patch.object(auth, "_ORIGINAL", side_effect=RuntimeError(raw)), \
             mock.patch.object(auth, "_cookie_session_state", return_value="missing"):
            with self.assertRaisesRegex(RuntimeError, "COOKIES_YT_B64") as caught:
                auth.download_youtube_file_guarded("https://youtu.be/test")
        self.assertNotIn("secret-id", str(caught.exception))
        self.assertNotIn("--cookies", str(caught.exception))

    def test_unknown_ytdlp_error_is_not_dumped_to_telegram(self):
        raw = "ERROR: signed private URL https://example.invalid/token=secret"
        with mock.patch.object(auth, "_ORIGINAL", side_effect=RuntimeError(raw)):
            with self.assertRaisesRegex(RuntimeError, "não concluiu o download") as caught:
                auth.download_youtube_file_guarded("https://youtu.be/test")
        self.assertNotIn("token=secret", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
