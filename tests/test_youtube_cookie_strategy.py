import importlib.util
import unittest
from pathlib import Path


_SPEC = importlib.util.spec_from_file_location("jetbot_sitecustomize_test", Path(__file__).resolve().parents[1] / "sitecustomize.py")
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)


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
        self.assertNotIn("mweb", joined)
        self.assertNotIn("android-vr", joined)
        self.assertNotIn("tv", joined)

    def test_player_response_failure_is_retryable(self):
        self.assertTrue(mod._retryable_youtube_error(RuntimeError("Failed to extract any player response")))


if __name__ == "__main__":
    unittest.main()
