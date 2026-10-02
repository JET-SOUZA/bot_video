import os

os.environ.setdefault("TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

import shopee_sourcemap_probe as probe


def test_source_map_url_uses_explicit_mapping_comment():
    js = 'console.log(1); //# sourceMappingURL=[postId]-abc.js.map'
    result = probe._source_map_url(
        "https://sv.shopee.com.br/share-web/_next/static/chunks/pages/share-video/[postId]-abc.js",
        js,
    )
    assert result.endswith("/[postId]-abc.js.map")


def test_route_strings_extracts_media_api_routes_only():
    source = (
        'const a="/api/v4/video/post/detail";'
        'const b="/v1/share/h5";'
        'const c="/assets/logo.svg";'
    )
    found = probe._route_strings(source)
    assert "/api/v4/video/post/detail" in found
    assert "/v1/share/h5" in found
    assert "/assets/logo.svg" not in found


def test_context_sanitizes_signed_urls():
    source = (
        'const video={watermarkVideoUrl:"https://cdn.example/video.mp4?sig=' + ('A' * 120) + '"};'
        'function load(postId){return request("/api/v4/video/post/detail",{postId})}'
    )
    joined = " ".join(probe._interesting_source_contexts(source))
    assert "watermarkVideoUrl" in joined
    assert "postId" in joined
    assert "https://cdn.example" not in joined
