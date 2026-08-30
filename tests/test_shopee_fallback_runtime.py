import os
import unittest
from unittest import mock

os.environ.setdefault("TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

import run_v2_fallback as fallback


class ShopeeFallbackPolicyTests(unittest.TestCase):
    def test_diagnostic_selector_can_recognize_marked_mp4(self):
        marked = "https://down-ws-br.vod.susercontent.com/api/v4/file.mp4"
        selected = fallback._select_playable_candidate(
            [("pageProps.mediaInfo.video.watermarkVideoUrl", marked)]
        )
        self.assertEqual(selected, marked)

    def test_cover_is_never_selected_as_video_fallback(self):
        cover = "https://cdn.example.com/video-cover.mp4"
        selected = fallback._select_playable_candidate(
            [("pageProps.mediaInfo.video.watermarkCoverUrl", cover)]
        )
        self.assertIsNone(selected)

    def test_original_is_still_preferred_before_fallback(self):
        clean = "https://cdn.example.com/original.mp4"
        with mock.patch.object(fallback, "_ORIGINAL_EXTRACT", return_value=clean), \
             mock.patch.object(fallback, "_fallback_shopee_media") as fallback_media:
            selected = fallback.extract_shopee_prefer_original("https://br.shp.ee/test")
        self.assertEqual(selected, clean)
        self.assertEqual(fallback._SOURCE_KIND.get(), "clean")
        fallback_media.assert_not_called()

    def test_marked_fallback_never_enters_production_extractor(self):
        marked = "https://cdn.example.com/marked.mp4"
        with mock.patch.object(fallback, "_ORIGINAL_EXTRACT", return_value=None), \
             mock.patch.object(fallback, "_fallback_shopee_media", return_value=marked) as fallback_media:
            result = fallback.extract_shopee_prefer_original("https://br.shp.ee/test")

        self.assertIsNone(result)
        self.assertIsNone(fallback._SOURCE_KIND.get())
        fallback_media.assert_not_called()

    def test_environment_cannot_reenable_marked_fallback(self):
        self.assertFalse(fallback._ALLOW_MARKED_FALLBACK)

    def test_clean_result_is_labeled_without_changing_the_file(self):
        clean = "https://cdn.example.com/original.mp4"

        def fake_strict(url, uid):
            self.assertEqual(fallback.extract_shopee_prefer_original(url), clean)
            return {"path": "/tmp/video.mp4", "source": "shopee-clean-strict"}

        with mock.patch.object(fallback, "_ORIGINAL_EXTRACT", return_value=clean), \
             mock.patch.object(fallback.runtime, "strict_download_media", side_effect=fake_strict), \
             mock.patch.object(fallback.runtime.app, "detect_platform", return_value="shopee"):
            result = fallback.download_media_with_shopee_policy("https://br.shp.ee/test", 1)

        self.assertEqual(result["source"], "shopee-clean")
        self.assertFalse(result["watermarked"])


if __name__ == "__main__":
    unittest.main()
