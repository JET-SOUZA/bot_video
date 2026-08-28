"""Shopee Video frontend API bridge for the V2 staging runtime.

The public share-video bundle calls an exported helper (``HP``) to load the
post payload.  This patch discovers that helper from the public JS already
served to browsers, reconstructs only a simple read payload containing the
public post id, and performs at most one matching read request per download.

It does not authenticate, bypass access controls, mutate Shopee state, or guess
private endpoints.  If discovery is ambiguous or the request is rejected, the
normal V2 fallback remains unchanged.
"""

import re
import threading
from urllib.parse import urljoin, urlparse

import run_v2 as runtime


_ORIGINAL_INSPECT = runtime._inspect_shopee_runtime
_ORIGINAL_EXTRACT = runtime.strict_extract_shopee_original
_LOCK = threading.Lock()
_DISCOVERY = {}

_BASE_RE = re.compile(r'\b([A-Za-z_$][\w$]*)=["\'](/v1/share/h5)["\']')
_CALL_RE = re.compile(
    r'([A-Za-z_$][\w$]*)\.Z\.(get|post)\(""\.concat\(([A-Za-z_$][\w$]*),["\']([^"\']+)["\']\),(\{.{0,700}?\})\)\.then',
    re.I | re.S,
)
_EXPORT_RE = re.compile(
    r'([A-Za-z_$][\w$]*):function\(\)\{return\s+([A-Za-z_$][\w$]*)\}',
    re.S,
)
_FUNC_RE = re.compile(r'([A-Za-z_$][\w$]*)=function\(([^)]*)\)\{return\s*$')


def _safe_text(value):
    text = re.sub(r"https?://[^\s\"']+", "<URL>", str(value or ""))
    text = re.sub(r"[A-Za-z0-9_\-]{80,}", "<LONG_TOKEN>", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:420]


def _function_before(js_text, position):
    prefix = (js_text or "")[max(0, position - 220):position]
    match = _FUNC_RE.search(prefix)
    if not match:
        return None, None
    args = [item.strip() for item in match.group(2).split(",") if item.strip()]
    return match.group(1), (args[0] if len(args) == 1 else None)


def _body_keys(body_expr, function_arg):
    """Return simple object keys whose value is the helper's sole argument."""
    if not function_arg:
        return []
    keys = []
    pattern = re.compile(
        r'(?:^|[,\{])\s*([A-Za-z_$][\w$]*)\s*:\s*' + re.escape(function_arg) + r'\s*(?=,|\})'
    )
    for match in pattern.finditer(body_expr or ""):
        key = match.group(1)
        if key not in keys:
            keys.append(key)
    return keys


def extract_frontend_api_calls(js_text):
    """Parse public minified bundle wrappers without executing JavaScript."""
    text = js_text or ""
    bases = {name: path for name, path in _BASE_RE.findall(text)}
    calls = []
    for match in _CALL_RE.finditer(text):
        _client, method, base_var, suffix, body = match.groups()
        base = bases.get(base_var)
        if base != "/v1/share/h5":
            continue
        function_name, function_arg = _function_before(text, match.start())
        if not function_name:
            continue
        calls.append(
            {
                "function": function_name,
                "arg": function_arg,
                "method": method.upper(),
                "route": base + suffix,
                "body_keys": _body_keys(body, function_arg),
                "body": _safe_text(body),
            }
        )

    exports = dict(_EXPORT_RE.findall(text))
    for call in calls:
        symbols = [symbol for symbol, fn in exports.items() if fn == call["function"]]
        call["exports"] = symbols
    return calls


def _scripts_from_html(html, page_url):
    scripts = []
    for match in re.finditer(r'<script[^>]+src=["\']([^"\']+\.js[^"\']*)["\']', html or "", re.I):
        src = match.group(1).replace("&amp;", "&")
        if "_next/static" not in src and "shareweb/static" not in src:
            continue
        scripts.append(urljoin(page_url, src))
    return list(dict.fromkeys(scripts))[:16]


def _discovery_key(page_url):
    return urlparse(page_url or "").path or str(page_url or "")


def _discover_from_public_bundles(html, page_url, headers):
    all_calls = []
    for script_url in _scripts_from_html(html, page_url):
        try:
            response = runtime.requests.get(script_url, timeout=15, headers=headers)
            if not response.ok:
                continue
            for call in extract_frontend_api_calls(response.text or ""):
                call = dict(call)
                call["bundle"] = urlparse(script_url).path.rsplit("/", 1)[-1][:120]
                if call not in all_calls:
                    all_calls.append(call)
        except Exception as exc:
            print(f"[JetBot Shopee] frontend API bundle scan failed: {type(exc).__name__}")

    # The share-video page calls g.HP(postId) before reading n.list[0].meta.
    # Prefer the exact HP export; do not guess another helper when it is absent.
    hp = next((call for call in all_calls if "HP" in call.get("exports", [])), None)
    with _LOCK:
        _DISCOVERY[_discovery_key(page_url)] = hp

    print(f"[JetBot Shopee] frontend_api discovered_calls={len(all_calls)} hp_found={bool(hp)}")
    for call in all_calls[:20]:
        export_text = ",".join(call.get("exports") or []) or "-"
        keys = ",".join(call.get("body_keys") or []) or "-"
        print(
            f"[JetBot Shopee] frontend_api_call export={export_text} function={call['function']} "
            f"method={call['method']} route={call['route']} body_keys={keys} bundle={call.get('bundle','-')}"
        )
    if hp:
        print(
            f"[JetBot Shopee] frontend_api HP method={hp['method']} route={hp['route']} "
            f"body_keys={','.join(hp.get('body_keys') or []) or '-'}"
        )
    return hp


def inspect_with_frontend_api(html, page_url, headers):
    result = _ORIGINAL_INSPECT(html, page_url, headers)
    try:
        _discover_from_public_bundles(html, page_url, headers)
    except Exception as exc:
        print(f"[JetBot Shopee] frontend API discovery failed: {type(exc).__name__}: {exc}")
    return result


def _read_only_candidate(call):
    if not call or call.get("method") not in {"GET", "POST"}:
        return False
    route = str(call.get("route") or "")
    if not route.startswith("/v1/share/h5/"):
        return False
    suffix = route.split("/v1/share/h5/", 1)[1].lower()
    blocked = (
        "like", "follow", "comment", "delete", "create", "reward", "report",
        "publish", "upload", "update", "set_", "add_", "remove", "send", "collect",
    )
    if any(token in suffix for token in blocked):
        return False
    return any(token in suffix for token in ("get", "video", "post", "media", "detail", "list"))


def _public_post_payload(call, share_id):
    keys = call.get("body_keys") or []
    if not keys:
        return None
    # Only reconstruct keys clearly referring to the public post/id argument.
    accepted = [key for key in keys if "post" in key.lower() or key.lower() in {"id", "video_id", "videoid"}]
    if not accepted:
        return None
    return {key: share_id for key in accepted}


def _clean_from_payload(payload):
    candidates = []
    for path, candidate in runtime.app._iter_media_candidates(payload):
        if not candidate or not str(candidate).startswith("http"):
            continue
        candidate = str(candidate)
        candidates.append((runtime._clean_score(path, candidate), path, candidate))
    candidates.sort(reverse=True, key=lambda item: item[0])
    for score, path, candidate in candidates:
        if runtime._marked_candidate(path, candidate):
            continue
        if not runtime._trusted_clean_candidate(path, candidate):
            continue
        parsed = urlparse(candidate)
        print(
            f"[JetBot Shopee] frontend_api clean candidate path={path} score={score} "
            f"host={parsed.netloc}"
        )
        return candidate
    return None


def _probe_hp(page_url, share_id, headers):
    with _LOCK:
        call = _DISCOVERY.get(_discovery_key(page_url))
    if not _read_only_candidate(call):
        print("[JetBot Shopee] frontend_api HP not safe/reconstructable for public read probe")
        return None
    payload = _public_post_payload(call, share_id)
    if not payload:
        print("[JetBot Shopee] frontend_api HP payload could not be reconstructed")
        return None

    endpoint = urljoin("https://sv.shopee.com.br/", call["route"].lstrip("/"))
    request_headers = dict(headers or {})
    request_headers.update({
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://sv.shopee.com.br",
        "Referer": page_url,
    })
    try:
        if call["method"] == "GET":
            response = runtime.requests.get(endpoint, params=payload, timeout=15, headers=request_headers)
        else:
            response = runtime.requests.post(endpoint, json=payload, timeout=15, headers=request_headers)
        print(
            f"[JetBot Shopee] frontend_api HP probe status={getattr(response, 'status_code', 0)} "
            f"method={call['method']} route={call['route']}"
        )
        if not response.ok:
            return None
        data = response.json()
        return _clean_from_payload(data)
    except Exception as exc:
        print(f"[JetBot Shopee] frontend_api HP probe failed: {type(exc).__name__}: {exc}")
        return None


def strict_extract_with_frontend_api(url):
    clean = _ORIGINAL_EXTRACT(url)
    if clean:
        return clean

    resolved = runtime.app._resolve_shopee(url)
    match = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", resolved)
    if not match:
        return None
    share_id = match.group(1)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Referer": "https://sv.shopee.com.br/",
    }
    candidate = _probe_hp(resolved, share_id, headers)
    if candidate:
        print("[JetBot Shopee] frontend_api original source selected")
        return candidate
    return None


runtime._inspect_shopee_runtime = inspect_with_frontend_api
runtime.strict_extract_shopee_original = strict_extract_with_frontend_api
runtime.app._extract_shopee_original_url = strict_extract_with_frontend_api
print("[JetBot Shopee] frontend public-API discovery patch loaded")
