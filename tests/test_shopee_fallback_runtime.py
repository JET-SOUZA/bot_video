import os
from unittest import mock

os.environ.setdefault("TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

import run_v2_fallback as fallback


def test_marked_mp4_can_be_used_as_playable_fallback():
    marked = "https://down-ws-br.vod.susercontent.com/api/v4/file.mp4"
    selected = fallback._select_playable_candidate(
        [("pageProps.mediaInfo.video.watermarkVideoUrl", marked)]
    )
    assert selected == marked


def test_cover_is_never_selected_as_video_fallback():
    cover = "https://cdn.example.com/video-cover.mp4"
    selected = fallback._select_playable_candidate(
        [("pageProps.mediaInfo.video.watermarkCoverUrl", cover)]
    )
    assert selected is None


def test_original_is_still_preferred_before_fallback():
    clean = "https://cdn.example.com/original.mp4"
    with mock.patch.object(fallback, "_ORIGINAL_EXTRACT", return_value=clean), \
         mock.patch.object(fallback, "_fallback_shopee_media") as fallback_media:
        assert fallback.extract_shopee_prefer_original("https://br.shp.ee/test") == clean
    fallback_media.assert_not_called()


def test_playable_media_is_returned_when_original_is_missing():
    marked = "https://cdn.example.com/marked.mp4"
    with mock.patch.object(fallback, "_ORIGINAL_EXTRACT", return_value=None), \
         mock.patch.object(fallback, "_fallback_shopee_media", return_value=marked):
        assert fallback.extract_shopee_prefer_original("https://br.shp.ee/test") == marked
