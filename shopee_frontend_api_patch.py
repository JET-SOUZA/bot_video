"""Shopee Video frontend API bridge for the V2 staging runtime.

The public share-video bundle calls an exported helper (``HP``) to load the
post payload. This patch discovers that helper from the public JS already
served to browsers, reconstructs only a simple read payload containing the
public post id, and performs at most one matching read request per download.

It does not authenticate, bypass access controls, mutate Shopee state, or guess
private endpoints. If discovery is ambiguous or the request is rejected, the
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
    r'([A-Za-z_$][\w$]*)\.Z\.(get|post)\(""\.concat\(([A-Za-z_$][\w$]*),["\']([^"\']+)["\']\),(\{.{0,1800}?\})\)(?:\.then|[,;)])',
    re.I | re.S,
)
_EXPORT_RE = re.compile(
    r'([A-Za-z_$][\w$]*):function\(\)\{return\s+([A-Za-z_$][\w$]*)\}',
    re.S,
)
_FUNC_RE = re.compile(r'([A-Za-z_$][\w$]*)=function\(([^)]*)\)\{return\s*$')
_ASSIGN_FUNC_RE = re.compile(r'\b([A-Za-z_$][\w$]*)\s*=\s*function\(([^)]*)\)\{', re.S)


def _safe_text(value):
    text = re.sub(r"https?://[^\s\"']+", "<URL>", str(value or ""))
    text = re.sub(r"[A-Za-z0-9_\-]{80,}", "<LONG_TOKEN>", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:520]


def _function_before(js_text, position):
    prefix = (js_text or "")[max(0, position - 520):position]
    matches = list(_ASSIGN_FUNC_RE.finditer(prefix))
    if not matches:
        return None, None
    match = matches[-1]
    args = [item.strip() for item in match.group(2).split(",") if item.strip()]
    return match.group(1), (args[0] if len(args) == 1 else None)


def _balanced_block(text, open_pos, open_char="{", close_char="}", limit=9000):
    if open_pos < 0 or open_pos >= len(text) or text[open_pos] != open_char:
        return None
    depth = 0
    quote = None
    escaped = False
    end = min(len(text), open_pos + limit)
    for index in range(open_pos, end):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in ("'", '"', "`"):
            quote = char
            continue
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return text[open_pos:index + 1]
    return None


def _function_body(text, function_name):
    pattern = re.compile(r'\b' + re.escape(function_name) + r'\s*=\s*function\(([^)]*)\)\{', re.S)
    match = pattern.search(text or "")
    if not match:
        return None, None
    open_pos = match.end() - 1
    block = _balanced_block(text, open_pos)
    if not block:
        return None, None
    args = [item.strip() for item in match.group(1).split(",") if item.strip()]
    return block[1:-1], (args[0] if len(args) == 1 else None)


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


def _calls_in_text(text, forced_function=None, forced_arg=None):
    bases = {name: path for name, path in _BASE_RE.findall(text or "")}
    calls = []
    for match in _CALL_RE.finditer(text or ""):
        _client, method, base_var, suffix, body = match.groups()
        base = bases.get(base_var)
        if base != "/v1/share/h5":
            continue
        function_name, function_arg = (forced_function, forced_arg)
        if not function_name:
            function_name, function_arg = _function_before(text, match.start())
        if not function_name:
            continue
        calls.append({
            "function": function_name,
            "arg": function_arg,
            "method": method.upper(),
            "route": base + suffix,
            "body_keys": _body_keys(body, function_arg),
            "body": _safe_text(body),
        })
    return calls


def _resolve_exported_helper(text, symbol):
    exports = dict(_EXPORT_RE.findall(text or ""))
    function_name = exports.get(symbol)
    if not function_name:
        return None
    body, function_arg = _function_body(text, function_name)
    if body is None:
        return {"function": function_name, "arg": function_arg, "exports": [symbol], "unresolved": True}

    # The base constant is often declared outside the helper body, so prepend a
    # small header containing all public /v1/share/h5 base assignments.
    bases = "\n".join(
        f'{name}="{path}";'
        for name, path in _BASE_RE.findall(text or "")
    )
    calls = _calls_in_text(bases + "\n" + body, forced_function=function_name, forced_arg=function_arg)
    for call in calls:
        call["exports"] = [symbol]
    if len(calls) == 1:
        return calls[0]
    if calls:
        # Prefer a read-like video/post/media route when the helper contains
        # auxiliary requests as well.
        preferred = [call for call in calls if _read_only_candidate(call)]
        if len(preferred) == 1:
            return preferred[0]
    return {
        "function": function_name,
        "arg": function_arg,
        "exports": [symbol],
        "unresolved": True,
        "candidate_calls": calls,
        "body_preview": _safe_text(body),
    }


def extract_frontend_api_calls(js_text):
    """Parse public minified bundle wrappers without executing JavaScript."""
    text = js_text or ""
    calls = _calls_in_text(text)
    exports = dict(_EXPORT_RE.findall(text))
    for call in calls:
        symbols = [symbol for symbol, fn in exports.items() if fn == call["function"]]
        call["exports"] = symbols

    # Resolve HP independently. The production Shopee bundle can place the
    # webpack export table far away from the actual request expression, which
    # made proximity-only parsing miss it.
    hp = _resolve_exported_helper(text, "HP")
    if hp and not hp.get("unresolved"):
        signature = (hp.get("function"), hp.get("method"), hp.get("route"), tuple(hp.get("body_keys") or []))
        existing = {
            (c.get("function"), c.get("method"), c.get("route"), tuple(c.get("body_keys") or []))
            for c in calls
        }
        if signature not in existing:
            calls.append(hp)
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
    hp_debug = []
    for script_url in _scripts_from_html(html, page_url):
        try:
            response = runtime.requests.get(script_url, timeout=15, headers=headers)
            if not response.ok:
                continue
            text = response.text or ""
            resolved_hp = _resolve_exported_helper(text, "HP")
            if resolved_hp:
                debug = dict(resolved_hp)
                debug["bundle"] = urlparse(script_url).path.rsplit("/", 1)[-1][:120]
                hp_debug.append(debug)
            for call in extract_frontend_api_calls(text):
                call = dict(call)
                call["bundle"] = urlparse(script_url).path.rsplit("/", 1)[-1][:120]
                key = (call.get("function"), call.get("method"), call.get("route"), tuple(call.get("body_keys") or []))
                if not any(
                    (item.get("function"), item.get("method"), item.get("route"), tuple(item.get("body_keys") or [])) == key
                    for item in all_calls
                ):
                    all_calls.append(call)
        except Exception as exc:
            print(f"[JetBot Shopee] frontend API bundle scan failed: {type(exc).__name__}")

    hp = next((call for call in all_calls if "HP" in call.get("exports", [])), None)
    with _LOCK:
        _DISCOVERY[_discovery_key(page_url)] = hp

    print(f"[JetBot Shopee] frontend_api discovered_calls={len(all_calls)} hp_found={bool(hp)}")
    for debug in hp_debug[:4]:
        if debug.get("unresolved"):
            candidates = debug.get("candidate_calls") or []
            print(
                f"[JetBot Shopee] frontend_api HP unresolved function={debug.get('function','-')} "
                f"arg={debug.get('arg') or '-'} candidate_calls={len(candidates)} "
                f"bundle={debug.get('bundle','-')} body={debug.get('body_preview','-')}"
            )
    for call in all_calls[:24]:
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
    return any(token in suffix for token in ("get", "video", "post", "media", "detail", "list", "feed"))


def _public_post_payload(call, share_id):
    keys = call.get("body_keys") or []
    if not keys:
        return None
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
    request_headers = runtime._augment_shopee_headers(dict(headers or {}))
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
    share_id = runtime._extract_shopee_share_id(resolved)
    if not share_id:
        return None
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Referer": "https://sv.shopee.com.br/",
    }
    runtime._augment_shopee_headers(headers)
    candidate = _probe_hp(resolved, share_id, headers)
    if candidate:
        print("[JetBot Shopee] frontend_api original source selected")
        return candidate
    return None


runtime._inspect_shopee_runtime = inspect_with_frontend_api
runtime.strict_extract_shopee_original = strict_extract_with_frontend_api
runtime.app._extract_shopee_original_url = strict_extract_with_frontend_api
print("[JetBot Shopee] frontend public-API discovery patch loaded")
