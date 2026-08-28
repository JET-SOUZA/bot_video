import os
import unittest
from unittest import mock

os.environ.setdefault("TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

import shopee_frontend_api_patch as api


class ShopeeFrontendApiTests(unittest.TestCase):
    def test_extracts_hp_export_and_post_route(self):
        js = (
            'var s="/v1/share/h5",getVideo=function(e){return a.Z.post('
            '"".concat(s,"/get_video_detail"),{postId:e}).then(function(e){return e.data})};'
            'n.d(t,{HP:function(){return getVideo}});'
        )
        calls = api.extract_frontend_api_calls(js)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["route"], "/v1/share/h5/get_video_detail")
        self.assertEqual(calls[0]["method"], "POST")
        self.assertEqual(calls[0]["body_keys"], ["postId"])
        self.assertIn("HP", calls[0]["exports"])

    def test_read_probe_rejects_mutation_route(self):
        call = {
            "method": "POST",
            "route": "/v1/share/h5/add_like",
            "body_keys": ["postId"],
        }
        self.assertFalse(api._read_only_candidate(call))

    def test_payload_only_uses_public_post_key(self):
        call = {"body_keys": ["postId", "user_id"]}
        self.assertEqual(api._public_post_payload(call, "abc=="), {"postId": "abc=="})

    def test_probe_selects_distinct_structured_clean_url(self):
        call = {
            "method": "POST",
            "route": "/v1/share/h5/get_video_detail",
            "body_keys": ["postId"],
        }
        page = "https://sv.shopee.com.br/share-video/abc=="
        with api._LOCK:
            api._DISCOVERY[api._discovery_key(page)] = call

        response = mock.Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "list": [{
                "meta": {"content": {"video": {
                    "url": "https://down-src-latam.vod.susercontent.com/master/original.mp4",
                    "watermarkVideoUrl": "https://down-ws-br.vod.susercontent.com/api/v4/marked.mp4",
                }}}
            }]
        }
        with mock.patch.object(api.runtime.requests, "post", return_value=response) as post:
            result = api._probe_hp(page, "abc==", {"User-Agent": "test"})
        self.assertIn("original.mp4", result)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs["json"], {"postId": "abc=="})


if __name__ == "__main__":
    unittest.main()
