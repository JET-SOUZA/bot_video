"""JetBot V2 runtime entrypoint.

Política estrita para Shopee Video: nunca entrega como original uma URL
proveniente de campo/rota marcada, nem uma URL sem evidência positiva de ser
fonte limpa. Também inspeciona payloads e bundles Next.js da página
compartilhada para tentar localizar a mídia master/original antes de desistir.
"""

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import requests
import yt_dlp

import jetbot_v2 as app


BAD_SHOPEE_HINTS = (
    "watermark",
    "watermarked",
    "watermarkvideourl",
    "watermark_video",
    "play_watermark",
    "with_watermark",
    "preview",
    "rendered",
    "render",
    "transcode",
    "logo",
    "cover",
    "thumb",
)

GOOD_SHOPEE_HINTS = (
    "original",
    "originalvideourl",
    "original_video",
    "origin",
    "source",
    "master",
    "raw",
    "upload",
    "download",
)

TRUSTED_SHOPEE_HINTS = GOOD_SHOPEE_HINTS


def _marked_candidate(path: str, url: str) -> bool:
    text = f"{path} {url}".lower()
    return any(hint in text for hint in BAD_SHOPEE_HINTS)


def _trusted_clean_candidate(path: str, url: str) -> bool:
    text = f"{path} {url}".lower()
    if _marked_candidate(path, url):
        return False
    return any(hint in text for hint in TRUSTED_SHOPEE_HINTS)


def _clean_score(path: str, url: str) -> int:
    text = f"{path} {url}".lower()
    score = app._rank_shopee_candidate(path, url)
    for hint in GOOD_SHOPEE_HINTS:
        if hint in text:
            score += 80
    if ".mp4" in text:
        score += 20
    if _marked_candidate(path, url):
        score -= 1000
    return score


def _iter_next_payloads(html: str, share_id: str, headers: dict):
    """Coleta __NEXT_DATA__ e os JSONs de hidratação do Next.js."""
    payloads = []
    try:
        match = re.search(
            r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
            html,
            re.S | re.I,
        )
        if not match:
            return payloads

        data = json.loads(match.group(1))
        payloads.append(("next_data", data))
        build_id = data.get("buildId") if isinstance(data, dict) else None
        if not build_id:
            return payloads

        encoded = quote(share_id, safe="")
        for data_url in (
            f"https://sv.shopee.com.br/share-web/_next/data/{build_id}/share-video/{encoded}.json",
            f"https://sv.shopee.com.br/_next/data/{build_id}/share-video/{encoded}.json",
        ):
            try:
                response = requests.get(data_url, timeout=15, headers=headers)
                content_type = (response.headers.get("content-type") or "").lower()
                if response.ok and "json" in content_type:
                    payloads.append(("next_json", response.json()))
            except Exception as exc:
                print(f"[JetBot Shopee] Next.js data fetch failed: {type(exc).__name__}: {exc}")
    except Exception as exc:
        print(f"[JetBot Shopee] Next.js parse failed: {type(exc).__name__}: {exc}")
    return payloads


def _extract_runtime_paths(js_text: str):
    """Extrai rotas relacionadas a vídeo/post/share presentes nos bundles."""
    found = set()
    for match in re.finditer(r'["\']([^"\']{4,260})["\']', js_text or ""):
        value = match.group(1).replace("\\/", "/")
        low = value.lower()
        if not any(token in low for token in ("video", "share", "post", "media")):
            continue
        if not any(token in low for token in ("/api/", "api/", "/video", "/post", "/share", "media")):
            continue
        if "_next/static" in low or "node_modules" in low:
            continue
        if len(value) > 240:
            continue
        found.add(value)
    return sorted(found)


def _inspect_shopee_runtime(html: str, page_url: str, headers: dict):
    """Lê bundles públicos carregados pela página e registra rotas úteis.

    Não chama rotas descobertas automaticamente; apenas registra strings de
    endpoint para que possamos identificar a API usada pelo front sem vazar
    URLs assinadas de mídia ou cookies.
    """
    if not html:
        return []
    scripts = []
    for match in re.finditer(r'<script[^>]+src=["\']([^"\']+\.js[^"\']*)["\']', html, re.I):
        src = match.group(1).replace("&amp;", "&")
        if "_next/static" not in src and "shareweb/static" not in src:
            continue
        scripts.append(urljoin(page_url, src))
    scripts = list(dict.fromkeys(scripts))[:16]

    endpoints = set()
    for script_url in scripts:
        try:
            response = requests.get(script_url, timeout=15, headers=headers)
            if not response.ok:
                continue
            text = response.text or ""
            for item in _extract_runtime_paths(text):
                endpoints.add(item)
        except Exception as exc:
            print(f"[JetBot Shopee] bundle fetch failed: {type(exc).__name__}: {exc}")

    ranked = sorted(
        endpoints,
        key=lambda value: (
            "original" not in value.lower() and "master" not in value.lower(),
            "video" not in value.lower(),
            len(value),
        ),
    )[:30]
    print(f"[JetBot Shopee] runtime bundles={len(scripts)} endpoint_candidates={len(ranked)}")
    for endpoint in ranked:
        safe = endpoint.replace("\n", " ")[:240]
        print(f"[JetBot Shopee] runtime_endpoint={safe}")
    return ranked


def _external_clean_source(url: str):
    """Usa somente um extrator configurado pelo dono do bot."""
    endpoint = (os.environ.get("SHOPEE_EXTRACTOR_URL") or "").strip()
    if not endpoint:
        return None
    try:
        response = requests.post(endpoint, json={"url": url}, timeout=20)
        response.raise_for_status()
        payload = response.json()
        candidate = payload.get("videoUrl") or payload.get("video_url") or payload.get("url")
        if not candidate or not str(candidate).startswith("http"):
            return None
        if _marked_candidate("external.original", str(candidate)):
            return None
        return str(candidate)
    except Exception as exc:
        print(f"[JetBot Shopee] external extractor failed: {type(exc).__name__}: {exc}")
        return None


def strict_extract_shopee_original(url: str):
    resolved = app._resolve_shopee(url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Referer": "https://sv.shopee.com.br/",
    }
    candidates = []
    html = ""

    try:
        page = requests.get(resolved, timeout=15, headers=headers)
        if page.ok:
            html = page.text
    except Exception as exc:
        print(f"[JetBot Shopee] page fetch failed: {type(exc).__name__}: {exc}")

    share_match = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", resolved)
    if not share_match and html:
        share_match = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", html)

    share_id = share_match.group(1) if share_match else None
    if share_id:
        for version in ("v4", "v2"):
            api_url = f"https://sv.shopee.com.br/api/{version}/share/video?shareVideoId={share_id}"
            try:
                response = requests.get(api_url, timeout=15, headers=headers)
                if response.ok:
                    for path, candidate in app._iter_media_candidates(response.json()):
                        candidates.append((f"api.{version}.{path}", candidate))
            except Exception as exc:
                print(f"[JetBot Shopee] {version} share API failed: {type(exc).__name__}: {exc}")

        if html:
            for label, payload in _iter_next_payloads(html, share_id, headers):
                for path, candidate in app._iter_media_candidates(payload):
                    candidates.append((f"{label}.{path}", candidate))

    if html:
        field_pattern = re.compile(
            r'"([^"\\]*(?:original|origin|source|master|raw|upload|download|play|video|watermark)[^"\\]*)"\s*:\s*"(https?:[^"\\]+)"',
            flags=re.IGNORECASE,
        )
        for match in field_pattern.finditer(html):
            raw = match.group(2).replace("\\u002F", "/").replace("\\/", "/")
            candidates.append((f"html.field.{match.group(1).lower()}", raw))

        for match in re.finditer(r"https?:\\?/\\?/[^\s\"'<>]+?(?:\.mp4|\.m3u8)[^\s\"'<>]*", html):
            raw = match.group(0).replace("\\/", "/")
            candidates.append(("html.unlabeled", raw))

    unique = {}
    for path, candidate in candidates:
        if not candidate or not str(candidate).startswith("http"):
            continue
        candidate = str(candidate)
        marked = _marked_candidate(path, candidate)
        trusted = _trusted_clean_candidate(path, candidate)
        score = _clean_score(path, candidate)
        current = unique.get(candidate)
        if current is None:
            unique[candidate] = (score, marked, trusted, path)
        else:
            # Nunca deixa uma aparição sem rótulo apagar a origem watermark.
            best_score = max(current[0], score)
            any_marked = current[1] or marked
            any_trusted = (current[2] or trusted) and not any_marked
            best_path = path if score > current[0] else current[3]
            unique[candidate] = (best_score, any_marked, any_trusted, best_path)

    ranked = sorted(
        ((url_value, *meta) for url_value, meta in unique.items()),
        key=lambda item: item[1],
        reverse=True,
    )

    for candidate, score, marked, trusted, path in ranked[:12]:
        parsed = urlparse(candidate)
        leaf = Path(parsed.path).name[:80] or "/"
        print(
            f"[JetBot Shopee] candidate path={path} score={score} marked={marked} "
            f"trusted={trusted} host={parsed.netloc} file={leaf}"
        )

    clean = [item for item in ranked if not item[2] and item[3]]
    if clean:
        candidate, score, _marked, _trusted, path = clean[0]
        print(f"[JetBot Shopee] trusted clean source selected path={path} score={score}")
        return candidate

    external = _external_clean_source(url)
    if external:
        print("[JetBot Shopee] clean source selected from configured extractor")
        return external

    # Última etapa de diagnóstico antes de falhar: descobrir as rotas reais
    # embutidas nos bundles atuais da página Shopee Video.
    _inspect_shopee_runtime(html, resolved, headers)

    print(
        f"[JetBot Shopee] CLEAN_SOURCE_NOT_FOUND share_id={share_id or 'unknown'} "
        f"candidates={len(ranked)}"
    )
    return None


def strict_download_media(url: str, uid: int):
    platform = app.detect_platform(url)
    if platform != "shopee":
        return _original_download_media(url, uid)

    temp_dir = Path(tempfile.mkdtemp(prefix=f"jetbot-{uid}-", dir=app.DOWNLOADS_DIR))
    cookiefile = app._temporary_cookiefile("shopee")
    try:
        clean_url = strict_extract_shopee_original(url)
        if not clean_url:
            raise RuntimeError(
                "Não encontrei uma fonte original confiável para este Shopee Vídeo. "
                "A versão marcada foi bloqueada e não será enviada como original."
            )

        if ".m3u8" in clean_url.lower():
            opts = app.build_general_ydl_options(temp_dir, "shopee", cookiefile)
            opts["outtmpl"] = str(temp_dir / "shopee-clean.%(ext)s")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(clean_url, download=True)
            media = app._find_media(temp_dir, ".mp4")
            title = (info or {}).get("title") or "Shopee Vídeo"
        else:
            media = app._download_direct(clean_url, temp_dir / "shopee-clean.mp4")
            title = "Shopee Vídeo"

        if not media or not Path(media).exists():
            raise RuntimeError("A fonte limpa foi localizada, mas o arquivo final não foi criado.")

        return {
            "path": str(media),
            "title": title,
            "platform": "shopee",
            "temp_dir": str(temp_dir),
            "source": "shopee-clean-strict",
        }
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    finally:
        app._safe_unlink(cookiefile)


_original_download_media = app.download_media
app._extract_shopee_original_url = strict_extract_shopee_original
app.download_media = strict_download_media


if __name__ == "__main__":
    app.main()
