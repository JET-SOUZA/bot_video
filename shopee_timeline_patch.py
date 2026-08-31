"""Patch específico para a rota pública revelada pelo helper HP da Shopee.

O bundle público da página share-video mostra que HP resolve para getTimelineVideo,
que faz GET em /api/v2/timeline/single com o parâmetro post_id. Este módulo
reconhece somente essa assinatura exata e tenta uma leitura pública do mesmo
endpoint usado pelo frontend. Nenhuma autenticação é burlada e nenhuma rota de
mutação é chamada.
"""

import re
from urllib.parse import urljoin, urlparse

import run_v2 as runtime
import shopee_frontend_api_patch as api


_ORIGINAL_INSPECT = runtime._inspect_shopee_runtime
_ORIGINAL_PROBE = api._probe_hp

_TIMELINE_RE = re.compile(
    r'([A-Za-z_$][\w$]*)\s*=\s*function\(([^)]*)\)\{return\s+([A-Za-z_$][\w$]*)\.Z\.get\(["\'](/api/v2/timeline/single)["\']\s*,\s*\{params:(.{0,2200}?)\}\)\.then',
    re.S,
)
_POST_ID_RE = re.compile(r'\bpost_id\s*:\s*([A-Za-z_$][\w$]*)\b')


def _scripts_from_html(html, page_url):
    scripts = []
    for match in re.finditer(r'<script[^>]+src=["\']([^"\']+\.js[^"\']*)["\']', html or "", re.I):
        src = match.group(1).replace("&amp;", "&")
        if "_next/static" not in src and "shareweb/static" not in src:
            continue
        scripts.append(urljoin(page_url, src))
    return list(dict.fromkeys(scripts))[:16]


def _find_timeline_call(js_text):
    text = js_text or ""
    for match in _TIMELINE_RE.finditer(text):
        function_name, args_text, _client, route, params_expr = match.groups()
        args = [item.strip() for item in args_text.split(",") if item.strip()]
        if not args:
            continue
        arg = args[0]
        post_match = _POST_ID_RE.search(params_expr)
        if not post_match or post_match.group(1) != arg:
            continue
        return {
            "function": function_name,
            "arg": arg,
            "method": "GET",
            "route": route,
            "body_keys": ["post_id"],
            "exports": ["HP"],
            "timeline_single": True,
        }
    return None


def _discover_timeline(html, page_url, headers):
    found = None
    for script_url in _scripts_from_html(html, page_url):
        try:
            response = runtime.requests.get(script_url, timeout=15, headers=headers)
            if not response.ok:
                continue
            call = _find_timeline_call(response.text or "")
            if call:
                call["bundle"] = urlparse(script_url).path.rsplit("/", 1)[-1][:120]
                found = call
                break
        except Exception as exc:
            print(f"[JetBot Shopee] timeline bundle scan failed: {type(exc).__name__}")
    if found:
        with api._LOCK:
            api._DISCOVERY[api._discovery_key(page_url)] = found
        print(
            f"[JetBot Shopee] timeline HP resolved method=GET route={found['route']} "
            f"params=post_id bundle={found.get('bundle','-')}"
        )
    else:
        print("[JetBot Shopee] timeline HP exact signature not found")
    return found


def inspect_with_timeline(html, page_url, headers):
    result = _ORIGINAL_INSPECT(html, page_url, headers)
    try:
        _discover_timeline(html, page_url, headers)
    except Exception as exc:
        print(f"[JetBot Shopee] timeline discovery failed: {type(exc).__name__}: {exc}")
    return result


def _probe_hp(page_url, share_id, headers):
    with api._LOCK:
        call = api._DISCOVERY.get(api._discovery_key(page_url))
    if not call or call.get("route") != "/api/v2/timeline/single" or call.get("method") != "GET":
        return _ORIGINAL_PROBE(page_url, share_id, headers)

    endpoint = urljoin("https://sv.shopee.com.br/", "api/v2/timeline/single")
    request_headers = runtime._augment_shopee_headers(dict(headers or {}))
    request_headers.update({
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://sv.shopee.com.br",
        "Referer": page_url,
    })
    try:
        response = runtime.requests.get(
            endpoint,
            params={"post_id": share_id},
            timeout=15,
            headers=request_headers,
        )
        print(
            f"[JetBot Shopee] timeline HP probe status={getattr(response, 'status_code', 0)} "
            "method=GET route=/api/v2/timeline/single params=post_id"
        )
        if not response.ok:
            return None
        payload = response.json()
        candidate = api._clean_from_payload(payload)
        if candidate:
            print("[JetBot Shopee] timeline original source selected")
            return candidate
        print("[JetBot Shopee] timeline response contained no trusted clean source")
        return None
    except Exception as exc:
        print(f"[JetBot Shopee] timeline HP probe failed: {type(exc).__name__}: {exc}")
        return None


runtime._inspect_shopee_runtime = inspect_with_timeline
api._probe_hp = _probe_hp
print("[JetBot Shopee] exact timeline-single patch loaded")
