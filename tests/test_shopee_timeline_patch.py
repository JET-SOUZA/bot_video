import os
import unittest
from unittest import mock

os.environ.setdefault("TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

import shopee_timeline_patch as timeline


class ShopeeTimelinePatchTests(unittest.TestCase):
    def test_finds_exact_timeline_single_signature(self):
        js = (
            'getTimelineVideo=function(e,t){return a.Z.get("/api/v2/timeline/single",'
            '{params:function(e){return e}({post_id:e},null!=t&&t.needProductV2?{need_product_v2:!0}:{}),baseURL:r})'
            '.then(function(e){return e.data})}'
        )
        call = timeline._find_timeline_call(js)
        self.assertIsNotNone(call)
        self.assertEqual(call["route"], "/api/v2/timeline/single")
        self.assertEqual(call["method"], "GET")
        self.assertEqual(call["body_keys"], ["post_id"])
        self.assertIn("HP", call["exports"])

    def test_probe_uses_only_public_post_id_param(self):
        page = "https://sv.shopee.com.br/share-video/abc=="
        call = {
            "method": "GET",
            "route": "/api/v2/timeline/single",
            "body_keys": ["post_id"],
            "exports": ["HP"],
            "timeline_single": True,
        }
        with timeline.api._LOCK:
            timeline.api._DISCOVERY[timeline.api._discovery_key(page)] = call

        response = mock.Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "list": [{"meta": {"content": {"video": {
                "url": "https://down-src-latam.vod.susercontent.com/master/original.mp4",
                "watermarkVideoUrl": "https://down-ws-br.vod.susercontent.com/api/v4/marked.mp4",
            }}}}]
        }
        with mock.patch.object(timeline.runtime.requests, "get", return_value=response) as get:
            result = timeline._probe_hp(page, "abc==", {"User-Agent": "test"})
        self.assertIn("original.mp4", result)
        self.assertEqual(get.call_args.kwargs["params"], {"post_id": "abc=="})


if __name__ == "__main__":
    unittest.main()
