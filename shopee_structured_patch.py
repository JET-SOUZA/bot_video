"""Narrow Shopee runtime patch based on the public share-video bundle shape.

The share page builds its playback object as roughly:
watermarkVideoUrl = video.watermarkVideoUrl || video.url

Therefore video.url is only promoted as a clean-source candidate when the same
structured video object also exposes a *different* watermarkVideoUrl.  Equal or
missing values are never promoted.  This avoids trusting unlabeled HTML URLs.
"""

import builtins
import sys


def _media_url(value):
    if not isinstance(value, str):
        return None
    value = value.replace("\\u002F", "/").replace("\\/", "/").replace("&amp;", "&")
    low = value.lower()
    if value.startswith("http") and any(token in low for token in (".mp4", ".m3u8", "video", "play")):
        return value
    return None


def _iter_distinct_video_sources(value, path=""):
    if isinstance(value, dict):
        # The runtime bundle shows both fields on the same video object.  Only
        # a distinct pair is evidence that `url` is not the marked rendition.
        clean = _media_url(value.get("url"))
        marked = _media_url(value.get("watermarkVideoUrl") or value.get("watermark_video_url"))
        if clean and marked and clean != marked:
            child = f"{path}.verified_original_source" if path else "verified_original_source"
            yield child.lower(), clean
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            yield from _iter_distinct_video_sources(item, child)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _iter_distinct_video_sources(item, f"{path}[{index}]")


def _patch_jetbot(module):
    if module is None or getattr(module, "_jetbot_structured_shopee_patch", False):
        return
    original = getattr(module, "_iter_media_candidates", None)
    if not callable(original):
        return

    def patched(value, path=""):
        seen = set()
        for item in original(value, path):
            seen.add(item)
            yield item
        for item in _iter_distinct_video_sources(value, path):
            if item not in seen:
                print("[JetBot Shopee] distinct structured video.url discovered")
                yield item

    module._iter_media_candidates = patched
    module._jetbot_structured_shopee_patch = True
    print("[JetBot Shopee] structured clean-source patch loaded")


_original_import = builtins.__import__


def _import(name, globals=None, locals=None, fromlist=(), level=0):
    module = _original_import(name, globals, locals, fromlist, level)
    if name == "jetbot_v2" or name.endswith(".jetbot_v2"):
        _patch_jetbot(sys.modules.get("jetbot_v2"))
    return module


if not getattr(builtins, "_jetbot_structured_import_patch", False):
    builtins.__import__ = _import
    builtins._jetbot_structured_import_patch = True
    _patch_jetbot(sys.modules.get("jetbot_v2"))
