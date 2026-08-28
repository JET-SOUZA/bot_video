import os
import unittest
from unittest import mock

os.environ.setdefault("TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

import run_v2 as runtime


class ShopeeRuntimeTests(unittest.TestCase):
    def test_watermark_field_is_rejected_even_with_opaque_url(self):
        url = "https://down-ws-br.vod.susercontent.com/api/v4/111/mms/file.mp4"
        self.assertTrue(runtime._marked_candidate("pageProps.mediaInfo.video.watermarkVideoUrl", url))
        self.assertFalse(runtime._trusted_clean_candidate("pageProps.mediaInfo.video.watermarkVideoUrl", url))

    def test_original_field_is_trusted(self):
        url = "https://down-src-latam.vod.susercontent.com/master/file.mp4"
        self.assertFalse(runtime._marked_candidate("media.originalVideoUrl", url))
        self.assertTrue(runtime._trusted_clean_candidate("media.originalVideoUrl", url))

    def test_runtime_path_extractor_finds_video_api_routes(self):
        js = (
            'const a="/api/v4/share/video?shareVideoId=";'
            'const b="/api/v4/video/post/detail";'
            'const c="/_next/static/chunks/main.js";'
        )
        found = runtime._extract_runtime_paths(js)
        self.assertIn("/api/v4/share/video?shareVideoId=", found)
        self.assertIn("/api/v4/video/post/detail", found)
        self.assertNotIn("/_next/static/chunks/main.js", found)

    def test_request_contexts_capture_share_route_without_exposing_signed_url(self):
        js = (
            'function x(e){return fetch("/v1/share/h5",{method:"POST",body:JSON.stringify({postId:e})})};'
            'const media="https://cdn.example.com/path/video.mp4?signature=' + ('A' * 120) + '";'
        )
        contexts = runtime._extract_request_contexts(js)
        joined = " ".join(contexts)
        self.assertIn("/v1/share/h5", joined)
        self.assertIn("postId", joined)
        self.assertNotIn("https://cdn.example.com", joined)

    def test_runtime_inspection_fetches_public_next_bundles(self):
        html = '<script src="/share-web/_next/static/chunks/pages/share-video/test.js"></script>'
        fake = mock.Mock()
        fake.ok = True
        fake.text = 'x="/api/v4/video/post/detail";fetch("/v1/share/h5",{body:JSON.stringify({postId:e})});'
        with mock.patch.object(runtime.requests, "get", return_value=fake) as get:
            found = runtime._inspect_shopee_runtime(html, "https://sv.shopee.com.br/share-video/abc", {})
        self.assertIn("/api/v4/video/post/detail", found)
        # The base inspector needs one request. Optional diagnostics such as the
        # public source-map probe may legitimately add requests for the same
        # static frontend asset and its .map file.
        self.assertGreaterEqual(get.call_count, 1)

    def test_shopee_download_never_falls_back_when_clean_source_missing(self):
        with mock.patch.object(runtime.app, "detect_platform", return_value="shopee"), \
             mock.patch.object(runtime, "strict_extract_shopee_original", return_value=None), \
             mock.patch.object(runtime.app, "_temporary_cookiefile", return_value=None), \
             mock.patch.object(runtime.tempfile, "mkdtemp", return_value="/tmp/jetbot-test"):
            with self.assertRaises(RuntimeError) as ctx:
                runtime.strict_download_media("https://br.shp.ee/test", 1)
        self.assertIn("fonte original confiável", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
