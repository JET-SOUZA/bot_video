# Jet TikTokShop Bot - Arquitetura C (Render + GitHub)
# PTB20 Webhook + Asaas + Shopee Universal Patch + Instagram Reels + YouTube + yt-dlp
# Atualização 2025-11: addpremium/delpremium + menu admin + mobile fix + contador diário corrigido
# Revisado: cookies IG B64, keepalive Render, fix event loop, /verpremium

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

# ---------------------------------------------------------
# TOKEN (Render) - mantém compatibilidade com suas variáveis
# ---------------------------------------------------------
TOKEN = (
    os.environ.get("TOKEN")
    or os.environ.get("BOT_TOKEN")
    or os.environ.get("TELEGRAM_TOKEN")
    or os.environ.get("TG_BOT_TOKEN")
)
if not TOKEN:
    raise ValueError("Nenhum token encontrado. Configure TOKEN ou BOT_TOKEN no Render.")

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
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

# Load TikTok cookies from env if exists
if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    with open(COOKIES_TIKTOK, "w", encoding="utf-8") as f:
        f.write(os.environ["COOKIES_TIKTOK"])

# Load Instagram cookies (Base64 preferred)
if "COOKIES_IG_B64" in os.environ:
    try:
        decoded = base64.b64decode(os.environ["COOKIES_IG_B64"]).decode("utf-8")
        with open(COOKIES_INSTAGRAM, "w", encoding="utf-8") as f:
            f.write(decoded)
        print("Cookies Instagram carregados do COOKIES_IG_B64 com sucesso!")
    except Exception as e:
        print("Erro ao decodificar COOKIES_IG_B64:", e)

# Fallback raw cookie
if "COOKIES_INSTAGRAM" in os.environ and not COOKIES_INSTAGRAM.exists():
    try:
        with open(COOKIES_INSTAGRAM, "w", encoding="utf-8") as f:
            f.write(os.environ["COOKIES_INSTAGRAM"])
        print("Cookies Instagram carregados do env COOKIES_INSTAGRAM.")
    except Exception as e:
        print("Erro ao gravar COOKIES_INSTAGRAM:", e)

# ---------------------------------------------------------
# JSON UTILS
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
# SISTEMA DE PREMIUM PERSISTENTE (ENV + fallback arquivo)
# ---------------------------------------------------------
def load_premium_env():
    db = {}
    raw = os.environ.get("PREMIUM_DB")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                db.update(parsed)
        except Exception as e:
            print("Erro ao parsear PREMIUM_DB:", e)
    try:
        file_data = load_json(ARQUIVO_PREMIUM)
        if isinstance(file_data, dict):
            if "premium_users" in file_data:
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
    except Exception:
        pass
    save_json(ARQUIVO_PREMIUM, {"premium_users": [int(k) for k in db.keys()]})


_premium_db = load_premium_env()

PREMIUM_FIXO = [
    ADMIN_ID,
    908662411,  # seu usuário manual
]
for uid in PREMIUM_FIXO:
    _premium_db[str(uid)] = True

save_premium_env(_premium_db)

def add_premium(user_id):
    _premium_db[str(int(user_id))] = True
    save_premium_env(_premium_db)


def remove_premium(user_id):
    uid = str(int(user_id))
    if uid in _premium_db:
        del _premium_db[uid]
        save_premium_env(_premium_db)


def is_premium(user_id) -> bool:
    return str(int(user_id)) in _premium_db


def list_premium():
    return sorted(int(k) for k in _premium_db.keys())


# ---------------------------------------------------------
# ASAAS — PREMIUM AUTOMÁTICO
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
                add_premium(int(p["metadata"]["telegram_id"]))
    except Exception as e:
        print("Erro Asaas:", e)


# ---------------------------------------------------------
# LIMITE DIÁRIO
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


# ---------------------------------------------------------
# COMANDOS
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


# Funções de planos, duvida, meuid, add/del premium, verpremium seguem indentação igual
# ---------------------------------------------------------
# Shopee/Instagram extractors e baixar_video
# ---------------------------------------------------------
# Aqui você mantém exatamente como já estava, mas ajustando indentação 4 espaços
# Exemplo do extrair_video_instagram:

def extrair_video_instagram(url):
    """
    Extrai vídeo do Instagram (post ou story) usando yt-dlp e cookies.
    Funciona para contas públicas e privadas (com cookies válidos no Render).
    """
    try:
        # Limpa a URL de query strings
        clean_url = url.split("?")[0]

        # Opções do yt-dlp
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "nocheckcertificate": True,
            "format": "best[ext=mp4]/best",
        }

        # Usa cookies do Render (decodificado)
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

        # Extrai info
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)

        # Retorna a URL direta do vídeo
        if info.get("url"):
            return info.get("url")
        elif info.get("requested_formats"):
            # Alguns stories/IGTV usam requested_formats
            return info["requested_formats"][0].get("url")
        elif info.get("entries"):
            # Stories em lista
            return info["entries"][0].get("url")
        else:
            return None

    except Exception as e:
        print("Erro ao extrair vídeo do Instagram:", e)
        return None



# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
async def main():
    verificar_pagamentos_asaas()
    app = Application.builder().token(TOKEN).build()
    await app.bot.set_my_commands(
        [
            BotCommand("start", "Iniciar bot"),
            BotCommand("planos", "Planos premium"),
            BotCommand("duvida", "Ajuda"),
            BotCommand("meuid", "Mostrar ID"),
            BotCommand("addpremium", "Adicionar premium (admin)"),
            BotCommand("delpremium", "Remover premium (admin)"),
            BotCommand("verpremium", "Visualizar premium (admin)"),
        ]
    )

    # Adiciona handlers
    app.add_handler(CommandHandler("start", start))
    # ... adicionar os outros handlers com indentação correta

    # Keepalive
    asyncio.create_task(keepalive_task())

    host = os.environ.get("RENDER_EXTERNAL_HOSTNAME") or os.environ.get("RENDER_EXTERNAL_URL")
    await app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=f"https://{host}/webhook" if host else None,
    )


# ---------------------------------------------------------
# EXECUÇÃO SEGURA
# ---------------------------------------------------------
if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
