"""Shopee Video diagnostics using public Next.js source maps.

This module does not bypass authentication and does not call undocumented media
endpoints. It only inspects public static JS/source-map assets already loaded by
the Shopee share page, looking for readable request paths and field names that
can explain where the clean media URL comes from.
"""

import json
import re
from urllib.parse import urljoin, urlparse

import run_v2 as runtime


_ORIGINAL_INSPECT = runtime._inspect_shopee_runtime


def _sanitize(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"https?://[^\s\"']+", "<URL>", text)
    text = re.sub(r"[A-Za-z0-9_\-]{80,}", "<LONG_TOKEN>", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:520]


def _interesting_source_contexts(source_text: str):
    text = source_text or ""
    needles = (
        "watermarkVideoUrl",
        "video.url",
        "postId",
        "shareVideo",
        "mediaInfo",
        "/v1/",
        "/api/",
        "fetch(",
        "axios",
        "request(",
    )
    contexts = []
    for needle in needles:
        start = 0
        while True:
            idx = text.find(needle, start)
            if idx < 0:
                break
            left = max(0, idx - 280)
            right = min(len(text), idx + len(needle) + 520)
            snippet = _sanitize(text[left:right])
            if snippet and snippet not in contexts:
                contexts.append(snippet)
            if len(contexts) >= 24:
                return contexts
            start = idx + len(needle)
    return contexts


def _route_strings(source_text: str):
    routes = set()
    patterns = (
        r'["\']((?:https?://|/)[^"\']{3,260})["\']',
        r'`((?:https?://|/)[^`]{3,260})`',
    )
    for pattern in patterns:
        for match in re.finditer(pattern, source_text or "", re.I):
            value = match.group(1).replace("\\/", "/")
            low = value.lower()
            if not any(token in low for token in ("video", "share", "post", "media", "/api/", "/v1/")):
                continue
            if "_next/static" in low:
                continue
            routes.add(value)
    return sorted(routes)


def _source_map_url(script_url: str, js_text: str):
    match = re.search(r"sourceMappingURL=([^\s*]+)", js_text or "", re.I)
    if match:
        return urljoin(script_url, match.group(1).strip())
    clean = script_url.split("?", 1)[0]
    return clean + ".map" if clean.endswith(".js") else None


def _inspect_source_maps(html: str, page_url: str, headers: dict):
    scripts = []
    for match in re.finditer(r'<script[^>]+src=["\']([^"\']+\.js[^"\']*)["\']', html or "", re.I):
        src = match.group(1).replace("&amp;", "&")
        low = src.lower()
        if "share-video" not in low and "video" not in low:
            continue
        scripts.append(urljoin(page_url, src))
    scripts = list(dict.fromkeys(scripts))[:4]

    total_sources = 0
    all_routes = set()
    contexts = []

    for script_url in scripts:
        try:
            js = runtime.requests.get(script_url, timeout=15, headers=headers)
            if not js.ok:
                continue
            map_url = _source_map_url(script_url, js.text or "")
            if not map_url:
                continue
            mapped = runtime.requests.get(map_url, timeout=15, headers=headers)
            if not mapped.ok:
                print(f"[JetBot Shopee] sourcemap unavailable file={urlparse(map_url).path.rsplit('/', 1)[-1][:100]}")
                continue
            payload = mapped.json() if hasattr(mapped, "json") else json.loads(mapped.text)
            source_names = payload.get("sources") or []
            source_contents = payload.get("sourcesContent") or []
            total_sources += len(source_contents)
            print(
                f"[JetBot Shopee] sourcemap loaded file={urlparse(map_url).path.rsplit('/', 1)[-1][:100]} "
                f"sources={len(source_contents)}"
            )
            for index, source_text in enumerate(source_contents):
                if not isinstance(source_text, str):
                    continue
                low = source_text.lower()
                if not any(token in low for token in ("video", "postid", "watermarkvideourl", "share")):
                    continue
                name = source_names[index] if index < len(source_names) else f"source_{index}"
                for route in _route_strings(source_text):
                    all_routes.add(route)
                for snippet in _interesting_source_contexts(source_text):
                    key = (name, snippet)
                    if key not in contexts:
                        contexts.append(key)
                    if len(contexts) >= 24:
                        break
                if len(contexts) >= 24:
                    break
        except Exception as exc:
            print(f"[JetBot Shopee] sourcemap probe failed: {type(exc).__name__}: {exc}")

    ranked_routes = sorted(
        all_routes,
        key=lambda value: (
            "/api/" not in value.lower() and "/v1/" not in value.lower(),
            "video" not in value.lower(),
            "share" not in value.lower(),
            len(value),
        ),
    )[:30]
    print(
        f"[JetBot Shopee] sourcemap summary scripts={len(scripts)} sources={total_sources} "
        f"routes={len(ranked_routes)} contexts={len(contexts)}"
    )
    for route in ranked_routes:
        print(f"[JetBot Shopee] sourcemap_route={_sanitize(route)}")
    for idx, (name, snippet) in enumerate(contexts[:24], 1):
        safe_name = re.sub(r"[^A-Za-z0-9_./@\-]", "_", str(name))[-140:]
        print(f"[JetBot Shopee] sourcemap_context_{idx} source={safe_name} text={snippet}")

    return ranked_routes


def inspect_with_source_maps(html: str, page_url: str, headers: dict):
    result = _ORIGINAL_INSPECT(html, page_url, headers)
    try:
        _inspect_source_maps(html, page_url, headers)
    except Exception as exc:
        print(f"[JetBot Shopee] sourcemap diagnostics failed: {type(exc).__name__}: {exc}")
    return result


runtime._inspect_shopee_runtime = inspect_with_source_maps
print("[JetBot Shopee] public sourcemap diagnostics loaded")
