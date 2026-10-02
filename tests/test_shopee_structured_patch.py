import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "shopee_structured_patch.py"
spec = importlib.util.spec_from_file_location("shopee_structured_patch_test", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def collect(payload):
    return list(module._iter_distinct_video_sources(payload))


def test_distinct_url_and_watermark_promotes_url():
    payload = {
        "mediaInfo": {
            "video": {
                "url": "https://cdn.example/original.mp4",
                "watermarkVideoUrl": "https://cdn.example/marked.mp4",
            }
        }
    }
    assert collect(payload) == [
        ("mediainfo.video.verified_original_source", "https://cdn.example/original.mp4")
    ]


def test_equal_url_and_watermark_is_not_promoted():
    payload = {
        "video": {
            "url": "https://cdn.example/same.mp4",
            "watermarkVideoUrl": "https://cdn.example/same.mp4",
        }
    }
    assert collect(payload) == []


def test_url_without_watermark_field_is_not_promoted():
    payload = {"video": {"url": "https://cdn.example/unknown.mp4"}}
    assert collect(payload) == []


def test_watermark_only_is_not_promoted():
    payload = {"video": {"watermarkVideoUrl": "https://cdn.example/marked.mp4"}}
    assert collect(payload) == []
