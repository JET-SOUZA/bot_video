# Jet TikTokShop Bot - Arquitetura C (Render + GitHub)
# PTB20 Webhook + Asaas + Shopee Universal Patch + yt-dlp
# (Versão ajustada: extrator reforçado para br.shp.ee / universal-link / share-video / APIs)

import os
import json
import requests
import asyncio
import traceback
from datetime import datetime, date
from pathlib import Path
from urllib.parse import unquote
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

import yt_dlp


# ---------------------------------------------------------
# TOKEN (Render)
# ---------------------------------------------------------
TOKEN = (
    os.environ.get("TOKEN") or
    os.environ.get("BOT_TOKEN") or
    os.environ.get("TELEGRAM_TOKEN") or
    os.environ.get("TG_BOT_TOKEN")
)

if not TOKEN:
    raise ValueError("Nenhum token encontrado. Configure TOKEN no Render.")


# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"

ADMIN_ID = 5593153639
LIMITE_DIARIO = 10
PORT = int(os.environ.get("PORT", 10000))

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

ARQUIVO_CONTADOR = SCRIPT_DIR / "downloads.json"
ARQUIVO_PREMIUM = SCRIPT_DIR / "premium.json"
COOKIES_TIKTOK = SCRIPT_DIR / "cookies.txt"

if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    with open(COOKIES_TIKTOK, "w") as f:
        f.write(os.environ["COOKIES_TIKTOK"])


# ---------------------------------------------------------
# JSON UTILS
# ---------------------------------------------------------
def load_json(path):
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


# ---------------------------------------------------------
# PREMIUM
# ---------------------------------------------------------
def load_premium():
    data = load_json(ARQUIVO_PREMIUM)
    return set(map(int, data.get("premium_users", [])))

def save_premium(users):
    save_json(ARQUIVO_PREMIUM, {"premium_users": list(users)})

USUARIOS_PREMIUM = load_premium()
USUARIOS_PREMIUM.add(ADMIN_ID)
save_premium(USUARIOS_PREMIUM)


# ---------------------------------------------------------
# ASAAS — PREMIUM AUTOMÁTICO
# ---------------------------------------------------------
def verificar_pagamentos_asaas():
    try:
        if not ASAAS_API_KEY:
            print("Asaas desativado. Sem API KEY.")
            return

        url = f"{ASAAS_BASE_URL}/payments?status=CONFIRMED&limit=100"
        headers = {"access_token": ASAAS_API_KEY}
        data = requests.get(url, headers=headers, timeout=10).json()

        for p in data.get("data", []):
            if "metadata" in p and "telegram_id" in p["metadata"]:
                uid = int(p["metadata"]["telegram_id"])
                USUARIOS_PREMIUM.add(uid)

        save_premium(USUARIOS_PREMIUM)

    except Exception as e:
        print("Erro Asaas:", e)


# ---------------------------------------------------------
# LIMITE DIÁRIO
# ---------------------------------------------------------
def verificar_limite(uid):
    data = load_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())

    if str(uid) not in data or data[str(uid)]["data"] != hoje:
        data[str(uid)] = {"data": hoje, "downloads": 0}
        save_json(ARQUIVO_CONTADOR, data)

    return data[str(uid)]["downloads"]

def incrementar_download(uid):
    data = load_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())

    if str(uid) not in data or data[str(uid)]["data"] != hoje:
        data[str(uid)] = {"data": hoje, "downloads": 1}
    else:
        data[str(uid)]["downloads"] += 1

    save_json(ARQUIVO_CONTADOR, data)
    return data[str(uid)]["downloads"]


# ---------------------------------------------------------
# COMANDOS
# ---------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *Jet TikTokShop Bot*\n\n"
        "Envie um link para baixar vídeo.\n"
        "⚠️ Free: 10/dia\n"
        "💎 Premium: ilimitado",
        parse_mode="Markdown"
    )

async def planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("💎 1 Mês – R$ 9,90", url="https://www.asaas.com/c/knu5vub6ejc2yyja")],
        [InlineKeyboardButton("💎 3 Meses – R$ 25,90", url="https://www.asaas.com/c/o9pg4uxrpgwnmqzd")],
        [InlineKeyboardButton("💎 1 Ano – R$ 89,90", url="https://www.asaas.com/c/puto9coszhwgprqc")],
    ]
    await update.message.reply_text("💎 Planos Premium:", reply_markup=InlineKeyboardMarkup(kb))

async def duvida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Suporte: lavimurtha@gmail.com")

async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Seu ID: {update.message.from_user.id}")


# ---------------------------------------------------------
# SHOPEE UNIVERSAL PATCH 2025 (REFORÇADO)
# ---------------------------------------------------------
def extrair_video_shopee(url):
    """
    Extrator reforçado para Shopee:
    - Resolve br.shp.ee (encurtadores) com GET e análise do HTML
    - Suporta universal-link?redir= (decodifica)
    - Extrai share-video ID e tenta múltiplas APIs:
      /api/v4/share/get_post?postId=
      /api/v4/item/get_video_info?postId=
      /api/v4/share/video?shareVideoId=
    - Faz buscas recursivas no JSON para encontrar URLs de mídia (.mp4 / .m3u8)
    - Fallback para regex no HTML final
    """
    from urllib.parse import unquote, urlparse, parse_qs
    import time
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "text/html,application/json,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://shopee.com.br/"
    }

    def find_media_in_obj(obj):
        """Recursively procura por strings .mp4/.m3u8 em dicts/listas/strings"""
        if isinstance(obj, str):
            s = obj
            m = re.search(r"https?://[^\s\"']+\.mp4[^\s\"']*", s)
            if m:
                return m.group(0)
            m2 = re.search(r"https?://[^\s\"']+\.m3u8[^\s\"']*", s)
            if m2:
                return m2.group(0)
            return None
        if isinstance(obj, dict):
            for k, v in obj.items():
                res = find_media_in_obj(v)
                if res:
                    return res
            return None
        if isinstance(obj, list):
            for v in obj:
                res = find_media_in_obj(v)
                if res:
                    return res
            return None
        return None

    # 1) if universal-link with redir parameter
    try:
        if "redir=" in url:
            # extract first redir param (works even if encoded twice)
            q = re.search(r"redir=([^&]+)", url)
            if q:
                decoded = unquote(q.group(1))
                # sometimes redir itself is encoded again
                decoded2 = unquote(decoded)
                url = decoded2
    except Exception:
        pass

    # 2) If shortener (shp.ee / br.shp.ee) do a GET and try to follow JS/meta redirects
    html_fallback = ""
    try:
        if "shp.ee" in url:
            r = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=12)
            url = r.url
            html_fallback = r.text or ""
            # If final URL still looks like a universal-link or contains redir, handle below
    except Exception:
        # try a simple HEAD as fallback
        try:
            r2 = requests.head(url, headers=HEADERS, allow_redirects=True, timeout=8)
            url = r2.url
        except Exception:
            pass

    # 2b) If we still have HTML from earlier (or can GET), attempt to detect client-side redirect patterns
    try:
        if not html_fallback:
            r = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=10)
            url = r.url
            html_fallback = r.text or ""
    except Exception:
        pass

    # check meta refresh
    try:
        m_meta = re.search(r'<meta[^>]+http-equiv=["\']?refresh["\']?[^>]*content=["\']?\d+;\s*url=([^"\' >]+)', html_fallback, flags=re.I)
        if m_meta:
            url_candidate = unquote(m_meta.group(1))
            url = url_candidate
    except Exception:
        pass

    # check window.location / location.replace / location.href patterns
    try:
        m_js = re.search(r'location(?:\.href|\.replace)?\s*=\s*["\']([^"\']+)["\']', html_fallback)
        if m_js:
            url_candidate = unquote(m_js.group(1))
            url = url_candidate
    except Exception:
        pass

    # check canonical link
    try:
        m_canon = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', html_fallback)
        if m_canon:
            url = m_canon.group(1)
    except Exception:
        pass

    # 3) extract share-video id from url or html
    share_match = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", url) or re.search(r"/share-video/([A-Za-z0-9=_\-]+)", html_fallback)
    share_id = None
    if share_match:
        share_id = share_match.group(1)

    # If share_id exists, try multiple APIs (with headers)
    tried = []
    if share_id:
        api_candidates = [
            f"https://sv.shopee.com.br/api/v4/share/get_post?postId={share_id}",
            f"https://sv.shopee.com.br/api/v4/item/get_video_info?postId={share_id}",
            f"https://sv.shopee.com.br/api/v4/share/video?shareVideoId={share_id}"
        ]
        for api_url in api_candidates:
            try:
                tried.append(api_url)
                r = requests.get(api_url, headers=HEADERS, timeout=10)
                # sometimes returns non-json with anti-bot; attempt safe parse
                try:
                    data = r.json()
                except Exception:
                    # if not json, maybe HTML — skip
                    data = None
                if data:
                    # search for media in known places first
                    candidates = []
                    # common locations
                    dd = data.get("data") if isinstance(data, dict) else None
                    if isinstance(dd, dict):
                        # mediaInfo
                        mi = dd.get("mediaInfo") if dd.get("mediaInfo") else dd
                        candidates.append(mi)
                        candidates.append(dd)
                    # also include whole JSON
                    candidates.append(data)

                    for c in candidates:
                        v = find_media_in_obj(c)
                        if v:
                            return v
            except Exception:
                # ignore and try next
                pass

    # 4) If no share_id or APIs failed, attempt to search the HTML fallback for mp4/m3u8 or JSON fields
    try:
        # if we haven't already fetched html_fallback, try now
        if not html_fallback:
            r = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=10)
            html_fallback = r.text or ""
            url = r.url
    except Exception:
        pass

    # regex search in HTML
    try:
        # quick mp4
        m_mp4 = re.search(r"https?://[^\s\"']+\.mp4[^\s\"']*", html_fallback)
        if m_mp4:
            return m_mp4.group(0)

        # quick m3u8
        m_m3 = re.search(r"https?://[^\s\"']+\.m3u8[^\s\"']*", html_fallback)
        if m_m3:
            return m_m3.group(0)

        # JSON-like "play_url" / "play" / "url" fields
        m_json_url = re.search(r'"(?:play_url|play|url|video_url)"\s*:\s*"([^"]+)"', html_fallback)
        if m_json_url:
            return m_json_url.group(1)

        # sometimes there is an encoded JSON blob: data-state or __NEXT_DATA__
        m_next = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>', html_fallback, flags=re.S)
        if m_next:
            try:
                nd = json.loads(m_next.group(1))
                found = find_media_in_obj(nd)
                if found:
                    return found
            except Exception:
                pass

        # sometimes there's a data object in JS
        m_jsobj = re.search(r'var\s+data\s*=\s*(\{.+?\});', html_fallback, flags=re.S)
        if m_jsobj:
            try:
                obj = json.loads(m_jsobj.group(1))
                found = find_media_in_obj(obj)
                if found:
                    return found
            except Exception:
                pass
    except Exception:
        pass

    # 5) Last-resort: try to build from share_id (some videos accessible via /api/v4/share/video)
    if share_id:
        try:
            fallback_api = f"https://sv.shopee.com.br/api/v4/share/video?shareVideoId={share_id}"
            r = requests.get(fallback_api, headers=HEADERS, timeout=10)
            try:
                data = r.json()
            except Exception:
                data = None
            if data:
                found = find_media_in_obj(data)
                if found:
                    return found
        except Exception:
            pass

    # nothing found
    return None


# ---------------------------------------------------------
# DOWNLOAD HANDLER
# ---------------------------------------------------------
async def baixar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    uid = update.message.from_user.id

    if not url.startswith("http"):
        return await update.message.reply_text("❌ Envie um link válido.")

    verificar_pagamentos_asaas()

    if uid not in USUARIOS_PREMIUM:
        usos = verificar_limite(uid)
        if usos >= LIMITE_DIARIO:
            return await update.message.reply_text("⚠️ Limite diário atingido.")

    # Patch Shopee
    if "shopee.com" in url or "shp.ee" in url or "sv.shopee.com" in url:
        await update.message.reply_text("🔄 Processando link da Shopee...")
        video_url = extrair_video_shopee(url)

        if not video_url:
            return await update.message.reply_text("❌ Não foi possível obter o vídeo da Shopee. (tente enviar o link longo ou mande o link br.shp.ee sem parâmetros)")

        url = video_url  # agora o yt-dlp baixa direto

    # ----------- yt-dlp ----------------------------------
    await update.message.reply_text("⏳ Baixando...")

    try:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        output = str(DOWNLOADS_DIR / f"%(id)s-{timestamp}.%(ext)s")

        ydl_opts = {
            "outtmpl": output,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "noplaylist": True,
        }

        if COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)

        def run(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        loop = asyncio.get_running_loop()
        file_path = await loop.run_in_executor(None, lambda: run(url))

        with open(file_path, "rb") as f:
            await update.message.reply_video(f, caption="✅ Seu vídeo está aqui!")

        os.remove(file_path)

        if uid not in USUARIOS_PREMIUM:
            novo = incrementar_download(uid)
            await update.message.reply_text(f"📊 Uso: {novo}/{LIMITE_DIARIO}")

    except Exception as e:
        traceback.print_exc()
        await update.message.reply_text(f"❌ Erro ao baixar: {e}")


# ---------------------------------------------------------
# MAIN (WEBHOOK)
# ---------------------------------------------------------
def main():
    verificar_pagamentos_asaas()

    app = Application.builder().token(TOKEN).build()

    async def set_commands(app):
        await app.bot.set_my_commands([
            BotCommand("start", "Iniciar bot"),
            BotCommand("planos", "Planos premium"),
            BotCommand("duvida", "Ajuda"),
            BotCommand("meuid", "Mostrar ID"),
        ])

    app.post_init = set_commands

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("planos", planos))
    app.add_handler(CommandHandler("duvida", duvida))
    app.add_handler(CommandHandler("meuid", meuid))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}/webhook"
    )


if __name__ == "__main__":
    main()
