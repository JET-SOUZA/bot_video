# Jet TikTokShop Bot - Arquitetura C (Render + GitHub)
# PTB20 Webhook + Asaas + Shopee Universal Patch + Instagram Reels + YouTube + yt-dlp
# Atualização 2025-11: addpremium/delpremium + menu admin + mobile fix + contador diário corrigido + premium fixo/dinâmico
# Revisado: cookies IG B64, keepalive Render, fix event loop, /verpremium detalhado

import os
import json
import requests
import asyncio
import traceback
import base64
from datetime import datetime, date
from pathlib import Path
from urllib.parse import unquote
import re
import secrets
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import yt_dlp
import nest_asyncio

# YT: import module
from youtube_downloader import download_youtube_file

# ---------------------------------------------------------
# CONFIGURAÇÕES
# ---------------------------------------------------------
TOKEN = (
    os.environ.get("TOKEN")
    or os.environ.get("BOT_TOKEN")
    or os.environ.get("TELEGRAM_TOKEN")
    or os.environ.get("TG_BOT_TOKEN")
)
if not TOKEN:
    raise ValueError("Nenhum token encontrado. Configure TOKEN ou BOT_TOKEN no Render.")

ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"
ADMIN_ID = int(os.environ.get("ADMIN_ID", "5593153639"))
LIMITE_DIARIO = int(os.environ.get("LIMITE_DIARIO", "10"))
PORT = int(os.environ.get("PORT", 10000))

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

ARQUIVO_CONTADOR = SCRIPT_DIR / "downloads.json"
ARQUIVO_PREMIUM = SCRIPT_DIR / "premium.json"
COOKIES_TIKTOK = SCRIPT_DIR / "cookies.txt"
COOKIES_INSTAGRAM = SCRIPT_DIR / "cookies_ig.txt"

# YT-specific counter file (separate)
ARQUIVO_CONTADOR_YT = SCRIPT_DIR / "downloads_youtube.json"
YT_FREE_LIMIT = 3
COOKIES_YOUTUBE = SCRIPT_DIR / "cookies_yt.txt"
YT_PENDING = {}  # token -> {"url":..., "uid":..., "ts":...}

# ---------------------------------------------------------
# CARREGAR COOKIES (TikTok / Instagram / YouTube via B64)
# ---------------------------------------------------------
if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    try:
        with open(COOKIES_TIKTOK, "w", encoding="utf-8") as f:
            f.write(os.environ["COOKIES_TIKTOK"])
        print("Cookies TikTok carregados do env COOKIES_TIKTOK.")
    except Exception as e:
        print("Erro ao gravar COOKIES_TIKTOK:", e)

if "COOKIES_IG_B64" in os.environ:
    try:
        decoded = base64.b64decode(os.environ["COOKIES_IG_B64"]).decode("utf-8")
        with open(COOKIES_INSTAGRAM, "w", encoding="utf-8") as f:
            f.write(decoded)
        print("Cookies Instagram carregados do COOKIES_IG_B64 com sucesso!")
    except Exception as e:
        print("Erro ao decodificar COOKIES_IG_B64:", e)

if "COOKIES_INSTAGRAM" in os.environ and not COOKIES_INSTAGRAM.exists():
    try:
        with open(COOKIES_INSTAGRAM, "w", encoding="utf-8") as f:
            f.write(os.environ["COOKIES_INSTAGRAM"])
        print("Cookies Instagram carregados do env COOKIES_INSTAGRAM.")
    except Exception as e:
        print("Erro ao gravar COOKIES_INSTAGRAM:", e)


def load_youtube_cookies_from_env():
    b64 = os.environ.get("COOKIES_YT_B64")
    if not b64:
        return None
    try:
        data = base64.b64decode(b64)
        with open(COOKIES_YOUTUBE, "wb") as f:
            f.write(data)
        print("Cookies YouTube carregados a partir de COOKIES_YT_B64.")
        return str(COOKIES_YOUTUBE)
    except Exception as e:
        print("Erro ao decodificar/gravar COOKIES_YT_B64:", e)
        return None

# ---------------------------------------------------------
# FUNÇÕES JSON
# ---------------------------------------------------------
def load_json(path: Path):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}


def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------
# SISTEMA DE PREMIUM
# ---------------------------------------------------------
def load_premium_env():
    raw = os.environ.get("PREMIUM_DB")
    db = {}
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                db.update(parsed)
        except Exception as e:
            print("Erro ao parsear PREMIUM_DB do ENV:", e)
    try:
        file_data = load_json(ARQUIVO_PREMIUM)
        if isinstance(file_data, dict):
            if "premium_users" in file_data and isinstance(file_data["premium_users"], list):
                for uid in file_data["premium_users"]:
                    db[str(uid)] = True
            else:
                for k, v in file_data.items():
                    if v:
                        db[str(k)] = True
    except Exception:
        pass
    return db


def save_premium_env(db: dict):
    try:
        os.environ["PREMIUM_DB"] = json.dumps(db)
    except Exception as e:
        print("Aviso: não foi possível gravar PREMIUM_DB no ENV:", e)
    try:
        ulist = [int(k) for k in db.keys()]
    except:
        ulist = []
    save_json(ARQUIVO_PREMIUM, {"premium_users": ulist})


_premium_db = load_premium_env()
PREMIUM_FIXO = {str(ADMIN_ID), "908662411"}
for uid in PREMIUM_FIXO:
    _premium_db[uid] = True
save_premium_env(_premium_db)


def add_premium(user_id):
    uid = str(int(user_id))
    _premium_db[uid] = True
    save_premium_env(_premium_db)


def remove_premium(user_id):
    uid = str(int(user_id))
    if uid in _premium_db and uid not in PREMIUM_FIXO:
        del _premium_db[uid]
    save_premium_env(_premium_db)


def is_premium(user_id) -> bool:
    return str(int(user_id)) in _premium_db


def list_premium():
    return sorted(int(k) for k in _premium_db.keys())


def get_premium_status():
    fixos = set(PREMIUM_FIXO)
    dinamicos = set(_premium_db.keys()) - fixos
    return fixos, dinamicos

# ---------------------------------------------------------
# ASAAS PREMIUM AUTOMÁTICO
# ---------------------------------------------------------
def verificar_pagamentos_asaas():
    try:
        if not ASAAS_API_KEY:
            print("Asaas desativado (sem API KEY).")
            return
        url = f"{ASAAS_BASE_URL}/payments?status=CONFIRMED&limit=100"
        headers = {"access_token": ASAAS_API_KEY}
        data = requests.get(url, headers=headers, timeout=10).json()
        for p in data.get("data", []):
            if "metadata" in p and "telegram_id" in p["metadata"]:
                uid = int(p["metadata"]["telegram_id"])
                add_premium(uid)
    except Exception as e:
        print("Erro Asaas:", e)

# ---------------------------------------------------------
# LIMITE DIÁRIO (Geral e YouTube)
# ---------------------------------------------------------
def verificar_limite(uid):
    data = load_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())
    if str(uid) not in data:
        data[str(uid)] = {"data": hoje, "downloads": 0}
        save_json(ARQUIVO_CONTADOR, data)
        return 0
    if data[str(uid)]["data"] != hoje:
        data[str(uid)]["data"] = hoje
        data[str(uid)]["downloads"] = 0
        save_json(ARQUIVO_CONTADOR, data)
    return data[str(uid)]["downloads"]


def incrementar_download(uid):
    data = load_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())
    if str(uid) not in data:
        data[str(uid)] = {"data": hoje, "downloads": 1}
    else:
        if data[str(uid)]["data"] != hoje:
            data[str(uid)]["data"] = hoje
            data[str(uid)]["downloads"] = 1
        else:
            data[str(uid)]["downloads"] += 1
    save_json(ARQUIVO_CONTADOR, data)
    return data[str(uid)]["downloads"]


def verificar_limite_youtube(uid):
    data = load_json(ARQUIVO_CONTADOR_YT)
    hoje = str(date.today())
    if str(uid) not in data:
        data[str(uid)] = {"data": hoje, "downloads": 0}
        save_json(ARQUIVO_CONTADOR_YT, data)
        return 0
    if data[str(uid)]["data"] != hoje:
        data[str(uid)]["data"] = hoje
        data[str(uid)]["downloads"] = 0
        save_json(ARQUIVO_CONTADOR_YT, data)
    return data[str(uid)]["downloads"]


def incrementar_download_youtube(uid):
    data = load_json(ARQUIVO_CONTADOR_YT)
    hoje = str(date.today())
    if str(uid) not in data:
        data[str(uid)] = {"data": hoje, "downloads": 1}
    else:
        if data[str(uid)]["data"] != hoje:
            data[str(uid)]["data"] = hoje
            data[str(uid)]["downloads"] = 1
        else:
            data[str(uid)]["downloads"] += 1
    save_json(ARQUIVO_CONTADOR_YT, data)
    return data[str(uid)]["downloads"]

# ---------------------------------------------------------
# COMANDOS BÁSICOS
# ---------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    texto = (
        "🎬 *Jet TikTokShop Bot*\n\n"
        "Envie um link para baixar vídeo.\n"
        "⚠️ Free: 10/dia\n"
        "💎 Premium: ilimitado"
    )
    botoes = [
        [InlineKeyboardButton("💎 Planos", callback_data="planos")],
        [InlineKeyboardButton("🆘 Suporte", callback_data="duvida")],
    ]
    if user_id == ADMIN_ID:
        botoes += [
            [InlineKeyboardButton("➕ Add Premium", callback_data="addpremium")],
            [InlineKeyboardButton("➖ Remover Premium", callback_data="delpremium")],
        ]
    await update.message.reply_text(
        texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes)
    )


async def planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("💎 1 Mês – R$ 9,90", url="https://www.asaas.com/c/knu5vub6ejc2yyja")],
        [InlineKeyboardButton("💎 3 Meses – R$ 25,90", url="https://www.asaas.com/c/o9pg4uxrpgwnmqzd")],
        [InlineKeyboardButton("💎 1 Ano – R$ 89,90", url="https://www.asaas.com/c/puto9coszhwgprqc")],
    ]
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            "💎 Planos Premium:", reply_markup=InlineKeyboardMarkup(kb)
        )
    else:
        await update.message.reply_text(
            "💎 Planos Premium:", reply_markup=InlineKeyboardMarkup(kb)
        )


async def duvida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("📞 Suporte: lavimurtha@gmail.com")
    else:
        await update.message.reply_text("📞 Suporte: lavimurtha@gmail.com")


async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Seu ID: {update.message.from_user.id}")


# ---------------------------------------------------------
# ADMIN COMANDOS
# ---------------------------------------------------------
async def addpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        return await update.callback_query.message.reply_text(
            "Use /addpremium <user_id> no chat (apenas admin)."
        )
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Apenas o admin pode usar este comando.")
    if not context.args:
        return await update.message.reply_text("Uso: /addpremium <user_id>")
    uid = int(context.args[0])
    add_premium(uid)
    await update.message.reply_text(f"✅ Usuário {uid} adicionado ao Premium!")


async def delpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        return await update.callback_query.message.reply_text(
            "Use /delpremium <user_id> no chat (apenas admin)."
        )
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Apenas o admin pode usar este comando.")
    if not context.args:
        return await update.message.reply_text("Uso: /delpremium <user_id>")
    uid = int(context.args[0])
    remove_premium(uid)
    await update.message.reply_text(f"❌ Usuário {uid} removido do Premium.")


# ---------------------------------------------------------
# /verpremium detalhado
# ---------------------------------------------------------
async def verpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Apenas o admin pode usar este comando.")
    fixos, dinamicos = get_premium_status()
    texto = "💎 *Usuários Premium:*\n\n"
    if fixos:
        texto += "📌 *Fixos (permanentes):*\n" + "\n".join(str(uid) for uid in sorted(fixos)) + "\n\n"
    else:
        texto += "📌 *Fixos (permanentes):* Nenhum\n\n"
    if dinamicos:
        texto += "⚡ *Dinâmicos (temporários/Asaas):*\n" + "\n".join(str(uid) for uid in sorted(dinamicos))
    else:
        texto += "⚡ *Dinâmicos (temporários/Asaas):* Nenhum"
    await update.message.reply_text(texto, parse_mode="Markdown")

# ---------------------------------------------------------
# Shopee Extractor
# ---------------------------------------------------------
def extrair_video_shopee(url):
    if "br.shp.ee" in url or "shp.ee" in url:
        try:
            r = requests.head(url, allow_redirects=True, timeout=10)
            url = r.url
        except:
            pass
    if "redir=" in url:
        try:
            redir = re.search(r"redir=([^&]+)", url).group(1)
            url = unquote(redir)
        except:
            pass
    m = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", url)
    if not m:
        try:
            html = requests.get(url, timeout=10).text
            m = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", html)
        except:
            pass
    if not m:
        return None
    share_id = m.group(1)
    api_url = f"https://sv.shopee.com.br/api/v4/share/video?shareVideoId={share_id}"
    try:
        data = requests.get(api_url, timeout=10).json()
    except:
        data = {}
    video_url = (
        data.get("data", {}).get("play")
        or data.get("data", {}).get("video_url")
        or data.get("data", {}).get("url")
        or (data.get("data", {}).get("videos", [{}])[0].get("url")
            if data.get("data", {}).get("videos")
            else None)
        or data.get("data", {}).get("path")
    )
    if not video_url:
        try:
            html = requests.get(url, timeout=10).text
            for regex in [
                r"https?://[^\s\"']+\.mp4",
                r"https?://[^\s\"']+\.m3u8[^\s\"']*",
                r'"url":"(https:[^"]+)"',
                r'"play[^"]*":"(https:[^"]+)"',
            ]:
                match = re.search(regex, html)
                if match:
                    return match.group(1) if len(match.groups()) else match.group(0)
        except:
            pass
    return video_url

# ---------------------------------------------------------
# Instagram Extractor
# ---------------------------------------------------------
def extrair_video_instagram(url):
    try:
        clean_url = url.split("?")[0]
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "nocheckcertificate": True,
            "format": "best[ext=mp4]/best",
        }
        if not COOKIES_INSTAGRAM.exists() and "COOKIES_IG_B64" in os.environ:
            try:
                decoded = base64.b64decode(os.environ["COOKIES_IG_B64"]).decode("utf-8")
                with open(COOKIES_INSTAGRAM, "w", encoding="utf-8") as f:
                    f.write(decoded)
                print("Cookies Instagram carregados do COOKIES_IG_B64 com sucesso!")
            except Exception as e:
                print("Erro ao decodificar COOKIES_IG_B64:", e)
        if COOKIES_INSTAGRAM.exists():
            ydl_opts["cookiefile"] = str(COOKIES_INSTAGRAM)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            if info.get("url"):
                return info.get("url")
            elif info.get("requested_formats"):
                return info["requested_formats"][0].get("url")
            elif info.get("entries"):
                return info["entries"][0].get("url")
            else:
                return None
    except Exception as e:
        print("Erro ao extrair vídeo do Instagram:", e)
        return None

# ---------------------------------------------------------
# YouTube Helper Functions
# ---------------------------------------------------------
def _make_yt_token():
    return secrets.token_hex(8)

def _cleanup_pending():
    now = time.time()
    to_del = []
    for k, v in list(YT_PENDING.items()):
        if now - v.get("ts", 0) > 20 * 60:
            to_del.append(k)
    for k in to_del:
        del YT_PENDING[k]

def _build_yt_keyboard(token: str, is_premium_user: bool, used: int):
    row1 = [
        InlineKeyboardButton("360p", callback_data=f"yt_start:{token}:360"),
        InlineKeyboardButton("480p", callback_data=f"yt_start:{token}:480"),
        InlineKeyboardButton("MP3", callback_data=f"yt_start:{token}:mp3"),
    ]
    if is_premium_user:
        row2 = [
            InlineKeyboardButton("720p", callback_data=f"yt_start:{token}:720"),
            InlineKeyboardButton("1080p", callback_data=f"yt_start:{token}:1080"),
            InlineKeyboardButton("2K", callback_data=f"yt_start:{token}:1440"),
        ]
        row3 = [InlineKeyboardButton("4K", callback_data=f"yt_start:{token}:2160")]
        status = InlineKeyboardButton("🔓 Premium: downloads ilimitados", callback_data="yt_info")
    else:
        row2 = [
            InlineKeyboardButton("720p 🔒", callback_data=f"yt_locked"),
            InlineKeyboardButton("1080p 🔒", callback_data=f"yt_locked"),
            InlineKeyboardButton("2K 🔒", callback_data=f"yt_locked"),
        ]
        row3 = [InlineKeyboardButton("4K 🔒", callback_data=f"yt_locked")]
        status = InlineKeyboardButton(f"🔢 YouTube: {used}/{YT_FREE_LIMIT} usados hoje", callback_data="yt_info")
    kb = [row1, row2, row3, [status]]
    return InlineKeyboardMarkup(kb)

# ---------------------------------------------------------
# DOWNLOAD HANDLER
# ---------------------------------------------------------
async def baixar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    uid = update.message.from_user.id
    if not url.startswith("http"):
        return await update.message.reply_text("❌ Envie um link válido.")
    verificar_pagamentos_asaas()
    if not is_premium(uid):
        usos = verificar_limite(uid)
        if usos >= LIMITE_DIARIO:
            return await update.message.reply_text("⚠️ Limite diário atingido.")

    if any(x in url for x in ["shopee.com", "shp.ee", "sv.shopee.com"]):
        await update.message.reply_text("🔄 Processando link da Shopee...")
        video_url = extrair_video_shopee(url)
        if not video_url:
            return await update.message.reply_text("❌ Não foi possível extrair vídeo da Shopee.")
        url = video_url
    elif any(x in url for x in ["instagram.com", "instagr.am", "ig.me"]):
        await update.message.reply_text("🔄 Processando link do Instagram...")
        video_url = extrair_video_instagram(url)
        if not video_url:
            return await update.message.reply_text("❌ Não foi possível extrair vídeo do Instagram (pode ser privado).")
        url = video_url
    elif any(x in url for x in ["youtube.com", "youtu.be"]):
        _cleanup_pending()
        token = _make_yt_token()
        YT_PENDING[token] = {"url": url, "uid": uid, "ts": time.time()}
        is_p = is_premium(uid)
        used = verificar_limite_youtube(uid)
        kb = _build_yt_keyboard(token, is_p, used)
        await update.message.reply_text("🎯 Escolha a qualidade do YouTube:", reply_markup=kb)
        return

    await update.message.reply_text("⏳ Baixando...")
    try:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        output = str(DOWNLOADS_DIR / f"%(id)s-{timestamp}.%(ext)s")
        ydl_opts = {
            "outtmpl": output,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "noplaylist": True,
            "postprocessors": [
                {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
                {"key": "FFmpegMetadata"},
                {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"},
            ],
            "postprocessor_args": ["-movflags", "faststart"],
        }
        if COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)
        if "instagram" in url and COOKIES_INSTAGRAM.exists():
            ydl_opts["cookiefile"] = str(COOKIES_INSTAGRAM)

        def run(url_local):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url_local, download=True)
                return ydl.prepare_filename(info)

        loop = asyncio.get_running_loop()
        file_path = await loop.run_in_executor(None, lambda: run(url))

        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                await update.message.reply_video(f, caption="✅ Seu vídeo está aqui!")
            try:
                os.remove(file_path)
            except:
                pass
        else:
            await update.message.reply_video(file_path, caption="✅ Seu vídeo está aqui!")

        if not is_premium(uid):
            novo = incrementar_download(uid)
            await update.message.reply_text(f"📊 Uso: {novo}/{LIMITE_DIARIO}")

    except Exception as e:
        traceback.print_exc()
        await update.message.reply_text(f"❌ Erro ao baixar: {e}")

# ---------------------------------------------------------
# CALLBACKQUERY HANDLER FUNÇÃO FUSIONADA
# ---------------------------------------------------------
async def callbacks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    uid = query.from_user.id

    # PLANOS / SUPORTE / ADMIN BUTTONS
    if data == "planos":
        # a função planos já chama query.answer()
        return await planos(update, context)
    if data == "duvida":
        # a função duvida já chama query.answer()
        return await duvida(update, context)
    if data == "addpremium":
        await query.answer()
        return await query.message.reply_text("Use: /addpremium <user_id>")
    if data == "delpremium":
        await query.answer()
        return await query.message.reply_text("Use: /delpremium <user_id>")

    # YOUTUBE FLOW
    if data == "yt_locked":
        return await query.answer("⚠️ Esta qualidade está disponível apenas para usuários Premium.", show_alert=True)
    if data == "yt_info":
        return await query.answer("Informação: escolha a qualidade para iniciar o download.", show_alert=False)

    if data.startswith("yt_start:"):
        # para essas ações mais longas, responda imediatamente (sem alert) para tirar o "loading"
        await query.answer()

        parts = data.split(":")
        if len(parts) != 3:
            return await query.answer("Erro interno (callback inválido).", show_alert=True)
        token = parts[1]
        quality = parts[2]
        pending = YT_PENDING.get(token)
        if not pending:
            return await query.answer("Sessão expirada. Envie o link novamente.", show_alert=True)
        if query.from_user.id != pending.get("uid"):
            return await query.answer("Esses botões não são para você.", show_alert=True)

        url = pending.get("url")
        to_mp3 = (quality == "mp3")

        if not is_premium(uid):
            used = verificar_limite_youtube(uid)
            if used >= YT_FREE_LIMIT:
                return await query.answer("⚠️ Limite diário do YouTube atingido (3 downloads).", show_alert=True)

        msg = await query.message.reply_text("⏳ Iniciando download... Por favor aguarde...")
        cookiefile_path = str(COOKIES_YOUTUBE) if COOKIES_YOUTUBE.exists() else None

        loop = asyncio.get_running_loop()

        def _download_blocking():
            try:
                path = download_youtube_file(
                    url, quality=quality, to_mp3=to_mp3, cookiefile=cookiefile_path
                )
                return {"ok": True, "path": path}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        result = await loop.run_in_executor(None, _download_blocking)
        if not result["ok"]:
            await msg.edit_text(f"❌ Erro ao baixar: {result.get('error', 'erro desconhecido')}")
            return

        filepath = result["path"]
        if not filepath or not os.path.exists(filepath):
            await msg.edit_text("❌ O download falhou (arquivo não encontrado).")
            return

        try:
            with open(filepath, "rb") as f:
                if to_mp3:
                    await query.message.reply_audio(f, title="Seu áudio 🎵")
                else:
                    await query.message.reply_video(f, caption="✅ Seu vídeo está aqui!")
        except Exception as e:
            await query.message.reply_text(f"❌ Erro ao enviar arquivo: {e}")

        try:
            os.remove(filepath)
        except:
            pass

        if not is_premium(uid):
            novo = incrementar_download_youtube(uid)
            await query.message.reply_text(f"📊 YouTube: {novo}/{YT_FREE_LIMIT}")


# ---------------------------------------------------------
# KEEPALIVE (Render Free / Ping)
# ---------------------------------------------------------
async def keepalive_task():
    while True:
        try:
            url = os.environ.get("RENDER_EXTERNAL_URL") or ""
            if url:
                try:
                    requests.get(url, timeout=5)
                except:
                    pass
        except:
            pass
        await asyncio.sleep(240)  # 4 min

# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
async def main():
    verificar_pagamentos_asaas()
    load_youtube_cookies_from_env()

    app = Application.builder().token(TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addpremium", addpremium))
    app.add_handler(CommandHandler("delpremium", delpremium))
    app.add_handler(CommandHandler("verpremium", verpremium))
    app.add_handler(CommandHandler("meuid", meuid))

    # Botão "Planos" do menu (reply keyboard)
app.add_handler(MessageHandler(filters.Regex(r'^(Planos|💎 Planos)$'), planos))

    # Mensagens de links para download
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

    # CallbackQuery handler (YouTube + Menu + Admin)
    app.add_handler(CallbackQueryHandler(callbacks_handler))

    # Start keepalive
    asyncio.create_task(keepalive_task())

    # Rodar no Render (webhook) ou local (polling)
    port = PORT
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        print("Rodando LOCAL (Polling)...")
        await app.run_polling()
        return

    print(f"Iniciando bot (webhook) na porta {port}...")
    await app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=TOKEN,
        webhook_url=f"{url}/{TOKEN}",
    )

# ---------------------------------------------------------
# RUN
# ---------------------------------------------------------
if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())




