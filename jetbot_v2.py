"""JetBot V2.

Preserva o comportamento público da main (Premium, Asaas, limites, menus,
admin, seletor YouTube e webhook) e troca apenas o motor de downloads,
além de ampliar as plataformas suportadas.
"""

import asyncio
import base64
import os
import re
import secrets
import shutil
import tempfile
import time
import traceback
from pathlib import Path
from urllib.parse import unquote

import requests
import yt_dlp
from telegram import BotCommand
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

# A main continua sendo a fonte de verdade para toda funcionalidade existente.
import bot as legacy

TOKEN = legacy.TOKEN
ADMIN_ID = legacy.ADMIN_ID
LIMITE_DIARIO = legacy.LIMITE_DIARIO
PORT = legacy.PORT
MAX_FILE_MB = int(os.environ.get("MAX_FILE_MB", "49"))
YT_FREE_LIMIT = legacy.YT_FREE_LIMIT
DOWNLOADS_DIR = legacy.DOWNLOADS_DIR
DOWNLOAD_DIR = legacy.DOWNLOAD_DIR

# Reexporta itens importantes para testes/revisão e compatibilidade.
is_premium = legacy.is_premium
add_premium = legacy.add_premium
remove_premium = legacy.remove_premium
verificar_limite = legacy.verificar_limite
incrementar_download = legacy.incrementar_download
verificar_limite_youtube = legacy.verificar_limite_youtube
incrementar_download_youtube = legacy.incrementar_download_youtube
_build_yt_keyboard = legacy._build_yt_keyboard
YT_PENDING = legacy.YT_PENDING

PLATFORM_NAMES = {
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "twitter": "X/Twitter",
    "youtube": "YouTube/Shorts",
    "shopee": "Shopee Vídeo",
    "pinterest": "Pinterest",
    "facebook": "Facebook",
    "reddit": "Reddit",
    "vimeo": "Vimeo",
    "generic": "vídeo",
}


def detect_platform(url: str) -> str:
    value = (url or "").lower()
    rules = [
        ("instagram", ("instagram.com", "instagr.am", "ig.me")),
        ("tiktok", ("tiktok.com", "vm.tiktok.com", "vt.tiktok.com")),
        ("twitter", ("twitter.com", "x.com")),
        ("youtube", ("youtube.com", "youtu.be")),
        ("shopee", ("shopee.com", "shp.ee", "sv.shopee.com")),
        ("pinterest", ("pinterest.", "pin.it")),
        ("facebook", ("facebook.com", "fb.watch")),
        ("reddit", ("reddit.com", "redd.it")),
        ("vimeo", ("vimeo.com",)),
    ]
    for platform, domains in rules:
        if any(domain in value for domain in domains):
            return platform
    return "generic"


def _cookie_payload(platform: str):
    keys = {
        "instagram": ("COOKIES_INSTAGRAM", "COOKIES_IG_B64"),
        "tiktok": ("COOKIES_TIKTOK", "COOKIES_TIKTOK_B64"),
        "youtube": ("COOKIES_YOUTUBE", "COOKIES_YT_B64"),
        "twitter": ("COOKIES_TWITTER", "COOKIES_X_B64"),
        "shopee": ("COOKIES_SHOPEE", "COOKIES_SHOPEE_B64"),
        "pinterest": ("COOKIES_PINTEREST", "COOKIES_PINTEREST_B64"),
        "facebook": ("COOKIES_FACEBOOK", "COOKIES_FACEBOOK_B64"),
        "reddit": ("COOKIES_REDDIT", "COOKIES_REDDIT_B64"),
        "vimeo": ("COOKIES_VIMEO", "COOKIES_VIMEO_B64"),
    }
    plain_key, b64_key = keys.get(
        platform,
        (f"COOKIES_{platform.upper()}", f"COOKIES_{platform.upper()}_B64"),
    )
    if os.environ.get(plain_key):
        return os.environ[plain_key]
    if os.environ.get(b64_key):
        try:
            return base64.b64decode(os.environ[b64_key]).decode("utf-8")
        except Exception as exc:
            print(f"Cookie B64 inválido para {platform}: {exc}")
    if os.environ.get("COOKIES_B64"):
        try:
            return base64.b64decode(os.environ["COOKIES_B64"]).decode("utf-8")
        except Exception:
            pass
    return None


def _temporary_cookiefile(platform: str):
    payload = _cookie_payload(platform)
    if not payload:
        return None
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=f"-{platform}.cookies.txt",
        delete=False,
    )
    try:
        handle.write(payload)
        return handle.name
    finally:
        handle.close()


def _safe_unlink(path):
    if path:
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:
            pass


def _find_media(directory: Path, preferred_suffix=None, prefix=None):
    candidates = []
    for item in directory.iterdir():
        if not item.is_file() or item.name.endswith(".part"):
            continue
        if prefix and not item.name.startswith(prefix):
            continue
        candidates.append(item)
    if preferred_suffix:
        preferred = [p for p in candidates if p.suffix.lower() == preferred_suffix]
        if preferred:
            return preferred[0]
    videos = [p for p in candidates if p.suffix.lower() in {".mp4", ".webm", ".mkv", ".mov"}]
    return (videos or candidates)[0] if candidates else None


def _resolve_shopee(url: str):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
        )
    }
    if "shp.ee" in url:
        try:
            url = requests.get(url, allow_redirects=True, timeout=12, headers=headers).url
        except Exception:
            pass
    if "redir=" in url:
        match = re.search(r"redir=([^&]+)", url)
        if match:
            try:
                url = unquote(match.group(1))
            except Exception:
                pass
    return url


def _download_direct(url: str, output: Path):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
        ),
        "Referer": "https://sv.shopee.com.br/",
    }
    with requests.get(url, stream=True, timeout=30, headers=headers) as response:
        response.raise_for_status()
        with output.open("wb") as file:
            for chunk in response.iter_content(chunk_size=512 * 1024):
                if chunk:
                    file.write(chunk)
    return output


def _iter_media_candidates(value, path=""):
    """Percorre respostas JSON/estruturas e encontra URLs de mídia."""
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            yield from _iter_media_candidates(item, child)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _iter_media_candidates(item, f"{path}[{index}]")
        return
    if not isinstance(value, str):
        return

    candidate = value.replace("\\u002F", "/").replace("\\/", "/").replace("&amp;", "&")
    if candidate.startswith("//"):
        candidate = "https:" + candidate
    if not candidate.startswith("http"):
        return
    lowered = candidate.lower()
    if any(ext in lowered for ext in (".mp4", ".m3u8", "video", "play")):
        yield path.lower(), candidate


def _rank_shopee_candidate(path: str, url: str):
    """Pontua URLs priorizando o arquivo original e penalizando versões marcadas."""
    text = f"{path} {url}".lower()
    score = 0
    for hint, points in (
        ("original", 80),
        ("origin", 70),
        ("source", 60),
        ("raw", 55),
        ("download", 45),
        ("video_url", 35),
        ("play_url", 30),
        ("play", 20),
        (".mp4", 25),
    ):
        if hint in text:
            score += points
    for hint, points in (
        ("watermark", 120),
        ("watermarked", 120),
        ("wm", 70),
        ("logo", 60),
        ("preview", 35),
        ("thumb", 80),
        ("cover", 80),
    ):
        if hint in text:
            score -= points
    if ".m3u8" in text:
        score -= 5
    return score


def _extract_shopee_original_url(url: str):
    """Tenta obter a fonte original da Shopee antes de baixar a versão renderizada.

    A Shopee muda campos/endpoints com frequência; por isso a função coleta
    candidatos tanto da API de compartilhamento quanto do HTML e escolhe a
    opção com sinais de mídia original, evitando explicitamente variantes com
    watermark/logo/preview quando existem alternativas.
    """
    resolved = _resolve_shopee(url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Referer": "https://sv.shopee.com.br/",
    }
    candidates = []

    share_match = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", resolved)
    if not share_match:
        try:
            page = requests.get(resolved, timeout=12, headers=headers)
            page.raise_for_status()
            html = page.text
            share_match = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", html)
        except Exception:
            html = ""
    else:
        try:
            html = requests.get(resolved, timeout=12, headers=headers).text
        except Exception:
            html = ""

    if share_match:
        share_id = share_match.group(1)
        api_urls = [
            f"https://sv.shopee.com.br/api/v4/share/video?shareVideoId={share_id}",
            f"https://sv.shopee.com.br/api/v2/share/video?shareVideoId={share_id}",
        ]
        for api_url in api_urls:
            try:
                response = requests.get(api_url, timeout=12, headers=headers)
                if response.ok:
                    payload = response.json()
                    candidates.extend(_iter_media_candidates(payload))
            except Exception:
                pass

    if html:
        # URLs explícitas no HTML/estado hidratado da página.
        for match in re.finditer(r"https?:\\?/\\?/[^\s\"'<>]+?(?:\.mp4|\.m3u8)[^\s\"'<>]*", html):
            raw = match.group(0).replace("\\/", "/")
            candidates.append(("html", raw))
        # Também captura campos JSON de vídeo sem depender do nome exato.
        for match in re.finditer(
            r'"([^"\\]*(?:original|origin|source|play|video)[^"\\]*)"\s*:\s*"(https?:[^"\\]+(?:\\.[^"\\]*)?)"',
            html,
            flags=re.IGNORECASE,
        ):
            raw = match.group(2).replace("\\u002F", "/").replace("\\/", "/")
            candidates.append((match.group(1).lower(), raw))

    # O extrator antigo continua útil como candidato, mas não ganha prioridade.
    try:
        legacy_url = legacy.extrair_video_shopee(url)
        if legacy_url:
            candidates.append(("legacy.play", legacy_url))
    except Exception:
        pass

    dedup = {}
    for path, candidate in candidates:
        if not candidate or not candidate.startswith("http"):
            continue
        dedup[candidate] = max(dedup.get(candidate, -10_000), _rank_shopee_candidate(path, candidate))
    if not dedup:
        return None

    ranked = sorted(dedup.items(), key=lambda item: item[1], reverse=True)
    for candidate, _score in ranked:
        lowered = candidate.lower()
        if not any(bad in lowered for bad in ("watermark", "watermarked", "logo=", "preview")):
            return candidate
    return ranked[0][0]


def build_general_ydl_options(temp_dir: Path, platform: str, cookiefile=None):
    opts = {
        "outtmpl": str(temp_dir / "%(title).120B-%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "format_sort": ["res:1080", "ext:mp4:m4a"],
        "merge_output_format": "mp4",
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 25,
        "postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
    }
    if cookiefile:
        opts["cookiefile"] = cookiefile
    if platform in {"instagram", "tiktok", "twitter", "facebook", "reddit"}:
        opts["http_headers"] = {"User-Agent": "Mozilla/5.0"}
    return opts


def download_media(url: str, uid: int):
    """Motor V2 para todas as plataformas exceto YouTube."""
    platform = detect_platform(url)
    if platform == "youtube":
        raise ValueError("YouTube usa o fluxo dedicado de qualidade/MP3.")

    original_url = url
    if platform == "shopee":
        url = _resolve_shopee(url)

    temp_dir = Path(tempfile.mkdtemp(prefix=f"jetbot-{uid}-", dir=DOWNLOADS_DIR))
    cookiefile = _temporary_cookiefile(platform)
    opts = build_general_ydl_options(temp_dir, platform, cookiefile)

    try:
        # Shopee: fonte original primeiro. Evita baixar a composição visual com
        # logo/tarja e dispensa qualquer delogo/borrão posterior.
        if platform == "shopee":
            clean_url = _extract_shopee_original_url(original_url)
            if clean_url:
                if ".m3u8" in clean_url.lower():
                    direct_opts = dict(opts)
                    direct_opts["outtmpl"] = str(temp_dir / "shopee-original.%(ext)s")
                    with yt_dlp.YoutubeDL(direct_opts) as ydl:
                        info = ydl.extract_info(clean_url, download=True)
                    media = _find_media(temp_dir, ".mp4")
                else:
                    media = _download_direct(clean_url, temp_dir / "shopee-original.mp4")
                    info = {"title": "Shopee Vídeo - original"}
                if media and Path(media).exists():
                    return {
                        "path": str(media),
                        "title": info.get("title") or "Shopee Vídeo",
                        "platform": platform,
                        "temp_dir": str(temp_dir),
                        "source": "shopee-original",
                    }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            media = _find_media(temp_dir, ".mp4")
            if not media:
                raise RuntimeError("Arquivo final não encontrado.")
            return {
                "path": str(media),
                "title": info.get("title") or "Vídeo",
                "platform": platform,
                "temp_dir": str(temp_dir),
                "source": "yt-dlp",
            }
        except yt_dlp.utils.DownloadError:
            # Mantém os extratores legados como último fallback de compatibilidade.
            direct_url = None
            if platform == "shopee":
                direct_url = legacy.extrair_video_shopee(original_url)
            elif platform == "instagram":
                direct_url = legacy.extrair_video_instagram(original_url)
            if not direct_url:
                raise
            media = _download_direct(direct_url, temp_dir / f"{platform}-fallback.mp4")
            return {
                "path": str(media),
                "title": PLATFORM_NAMES[platform],
                "platform": platform,
                "temp_dir": str(temp_dir),
                "source": "legacy-fallback",
            }
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    finally:
        _safe_unlink(cookiefile)


def build_youtube_ydl_options(output_dir: Path, prefix: str, quality: str, to_mp3: bool, cookiefile=None):
    opts = {
        "outtmpl": str(output_dir / f"{prefix}-%(id)s.%(ext)s"),
        "noplaylist": True,
        # A playlist-only URL cannot be converted to a single-video URL by
        # noplaylist.  The Telegram flow returns one file, so cap it explicitly
        # to the first item instead of downloading an unbounded playlist.
        "playlist_items": "1",
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 25,
    }
    if cookiefile:
        opts["cookiefile"] = cookiefile

    if to_mp3:
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    else:
        height = int(quality)
        opts["format"] = f"bv*[height<={height}]+ba/b[height<={height}]/b"
        opts["format_sort"] = [f"res:{height}", "ext:mp4:m4a"]
        opts["merge_output_format"] = "mp4"
        opts["postprocessors"] = [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}
        ]
    return opts


def download_youtube_file_v2(url, quality="1080", to_mp3=False, cookiefile=None):
    """Substitui apenas o motor usado pelo callback YouTube da main.

    A UI, bloqueios Premium e contador continuam sendo executados pelo
    callbacks_handler original de bot.py.
    """
    del cookiefile
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    prefix = f"v2-{int(time.time())}-{secrets.token_hex(4)}"
    runtime_cookie = _temporary_cookiefile("youtube")
    opts = build_youtube_ydl_options(
        DOWNLOAD_DIR,
        prefix,
        "360" if to_mp3 else quality,
        to_mp3,
        runtime_cookie,
    )
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
        media = _find_media(
            DOWNLOAD_DIR,
            ".mp3" if to_mp3 else ".mp4",
            prefix=prefix,
        )
        if not media:
            raise RuntimeError("O download falhou (arquivo final não encontrado).")
        return str(media)
    except Exception:
        for item in list(DOWNLOAD_DIR.glob(f"{prefix}-*")):
            _safe_unlink(item)
        raise
    finally:
        _safe_unlink(runtime_cookie)


# Força o callback legado a usar o novo downloader blocking, que respeita
# quality e MP3. Isso preserva integralmente o restante do fluxo existente.
legacy.baixar_video_youtube = None
legacy.download_youtube_file = download_youtube_file_v2


async def baixar_video(update, context):
    """Handler V2: mantém regras existentes e amplia plataformas."""
    url = (update.message.text or "").strip()
    uid = update.message.from_user.id

    if not url.startswith("http"):
        return await update.message.reply_text("❌ Envie um link válido.")

    legacy.verificar_pagamentos_asaas()

    if not legacy.is_premium(uid):
        usos = legacy.verificar_limite(uid)
        if usos >= legacy.LIMITE_DIARIO:
            return await update.message.reply_text("⚠️ Limite diário atingido.")

    platform = detect_platform(url)

    if platform == "youtube":
        legacy._cleanup_pending()
        token = legacy._make_yt_token()
        legacy.YT_PENDING[token] = {"url": url, "uid": uid, "ts": time.time()}
        keyboard = legacy._build_yt_keyboard(
            token,
            legacy.is_premium(uid),
            legacy.verificar_limite_youtube(uid),
        )
        await update.message.reply_text(
            "🎯 Escolha a qualidade do YouTube:",
            reply_markup=keyboard,
        )
        return

    status = await update.message.reply_text(
        f"⏳ Baixando de {PLATFORM_NAMES.get(platform, 'vídeo')}..."
    )
    result = None
    try:
        result = await asyncio.to_thread(download_media, url, uid)
        path = Path(result["path"])
        if path.stat().st_size > MAX_FILE_MB * 1024 * 1024:
            await status.edit_text(
                f"⚠️ O arquivo ficou maior que {MAX_FILE_MB} MB e não pode ser enviado por este bot."
            )
            return
        await status.edit_text("📤 Enviando para o Telegram...")
        with path.open("rb") as media:
            video_kwargs = {
                "caption": "✅ Seu vídeo está aqui!",
                "supports_streaming": True,
            }
            for field in ("width", "height", "duration"):
                if result.get(field):
                    video_kwargs[field] = result[field]
            await update.message.reply_video(
                media,
                **video_kwargs,
            )
        if not legacy.is_premium(uid):
            novo = legacy.incrementar_download(uid)
            await update.message.reply_text(f"📊 Uso: {novo}/{legacy.LIMITE_DIARIO}")
        try:
            await status.delete()
        except Exception:
            pass
    except yt_dlp.utils.DownloadError as exc:
        message = str(exc).lower()
        if "cookies" in message or "login" in message or "sign in" in message:
            text = "A plataforma exigiu autenticação/cookies. Configure-os apenas nos Secrets do Render."
        else:
            text = "Não foi possível baixar esse link. Ele pode ser privado, removido ou protegido."
        await status.edit_text(f"❌ {text}")
    except Exception as exc:
        traceback.print_exc()
        await status.edit_text(f"❌ Erro ao baixar: {type(exc).__name__}: {exc}")
    finally:
        if result and result.get("temp_dir"):
            shutil.rmtree(result["temp_dir"], ignore_errors=True)


async def _post_init(application: Application):
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Iniciar o bot"),
            BotCommand("meuid", "Mostrar seu ID"),
            BotCommand("addpremium", "Adicionar usuário premium (admin)"),
            BotCommand("delpremium", "Remover usuário premium (admin)"),
            BotCommand("verpremium", "Listar usuários premium (admin)"),
        ]
    )
    asyncio.create_task(legacy.keepalive_task())


def build_application():
    """Cria o bot sem iniciar rede; usado também pelos smoke tests."""
    app = Application.builder().token(TOKEN).post_init(_post_init).build()

    app.add_handler(CommandHandler("start", legacy.start))
    app.add_handler(CommandHandler("addpremium", legacy.addpremium))
    app.add_handler(CommandHandler("delpremium", legacy.delpremium))
    app.add_handler(CommandHandler("verpremium", legacy.verpremium))
    app.add_handler(CommandHandler("meuid", legacy.meuid))

    app.add_handler(
        MessageHandler(
            filters.Regex(r"^(Planos|💎 Planos)$"),
            legacy.planos,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            baixar_video,
        )
    )

    app.add_handler(CallbackQueryHandler(legacy.callbacks_handler))
    return app


def main():
    legacy.verificar_pagamentos_asaas()
    app = build_application()
    url = os.environ.get("RENDER_EXTERNAL_URL")

    if not url:
        print("Rodando LOCAL (Polling)...")
        app.run_polling()
        return

    print(f"Iniciando bot (webhook) na porta {PORT}...")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{url}/{TOKEN}",
    )


if __name__ == "__main__":
    main()
