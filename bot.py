# ---------------------------------------------------------
# Jet TikTokShop Bot - Corrigido Webhook + Premium + Download
# ---------------------------------------------------------

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

# -------------------------
# TOKEN E CONFIGURAÇÃO
# -------------------------
TOKEN = os.environ.get("TOKEN") or os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("TOKEN do bot não encontrado.")

ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
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

# -------------------------
# COOKIES INSTAGRAM
# -------------------------
if "COOKIES_IG_B64" in os.environ:
    try:
        decoded = base64.b64decode(os.environ["COOKIES_IG_B64"]).decode("utf-8")
        with open(COOKIES_INSTAGRAM, "w", encoding="utf-8") as f:
            f.write(decoded)
        print("Cookies Instagram carregados do COOKIES_IG_B64 com sucesso!")
    except Exception as e:
        print("Erro ao decodificar COOKIES_IG_B64:", e)

# -------------------------
# UTILIDADES JSON
# -------------------------
def load_json(path: Path):
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# -------------------------
# PREMIUM
# -------------------------
def load_premium_env():
    db = {}
    raw = os.environ.get("PREMIUM_DB")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                db.update(parsed)
        except:
            pass
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
    except:
        pass
    return db

def save_premium_env(db: dict):
    try:
        os.environ["PREMIUM_DB"] = json.dumps(db)
    except:
        pass
    save_json(ARQUIVO_PREMIUM, {"premium_users": [int(k) for k in db.keys()]})

_premium_db = load_premium_env()
PREMIUM_FIXO = [ADMIN_ID, 908662411]
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

# -------------------------
# ASAAS
# -------------------------
def verificar_pagamentos_asaas():
    if not ASAAS_API_KEY:
        return
    try:
        url = f"https://www.asaas.com/api/v3/payments?status=CONFIRMED&limit=100"
        headers = {"access_token": ASAAS_API_KEY}
        data = requests.get(url, headers=headers, timeout=10).json()
        for p in data.get("data", []):
            if "metadata" in p and "telegram_id" in p["metadata"]:
                add_premium(int(p["metadata"]["telegram_id"]))
    except:
        pass

# -------------------------
# LIMITE DIÁRIO
# -------------------------
def verificar_limite(uid):
    data = load_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())
    if str(uid) not in data or data[str(uid)]["data"] != hoje:
        data[str(uid)] = {"data": hoje, "downloads": 0}
        save_json(ARQUIVO_CONTADOR, data)
        return 0
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

# -------------------------
# COMANDOS
# -------------------------
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
    await update.message.reply_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))

# ---------- PLANOS / SUPORTE / MEUID ----------
async def planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("💎 1 Mês – R$ 9,90", url="https://www.asaas.com/c/knu5vub6ejc2yyja")],
        [InlineKeyboardButton("💎 3 Meses – R$ 25,90", url="https://www.asaas.com/c/o9pg4uxrpgwnmqzd")],
        [InlineKeyboardButton("💎 1 Ano – R$ 89,90", url="https://www.asaas.com/c/puto9coszhwgprqc")],
    ]
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("💎 Planos Premium:", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text("💎 Planos Premium:", reply_markup=InlineKeyboardMarkup(kb))

async def duvida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("📞 Suporte: lavimurtha@gmail.com")
    else:
        await update.message.reply_text("📞 Suporte: lavimurtha@gmail.com")

async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Seu ID: {update.message.from_user.id}")

# ---------- ADMIN ----------
async def addpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        return await update.callback_query.message.reply_text("Use /addpremium <user_id> no chat.")
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
        return await update.callback_query.message.reply_text("Use /delpremium <user_id> no chat.")
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Apenas o admin pode usar este comando.")
    if not context.args:
        return await update.message.reply_text("Uso: /delpremium <user_id>")
    uid = int(context.args[0])
    remove_premium(uid)
    await update.message.reply_text(f"❌ Usuário {uid} removido do Premium.")

async def verpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Apenas o admin.")
    users = list_premium()
    if not users:
        return await update.message.reply_text("Nenhum usuário premium.")
    lista = "\n".join(str(uid) for uid in users)
    await update.message.reply_text(f"💎 Usuários Premium:\n{lista}", parse_mode="Markdown")

# ---------- CALLBACK HANDLER ----------
async def callbacks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = (query.data or "").lower()
    if data == "planos":
        await planos(update, context)
    elif data == "duvida":
        await duvida(update, context)
    elif data == "addpremium":
        await addpremium(update, context)
    elif data == "delpremium":
        await delpremium(update, context)
    else:
        await query.answer()

# ---------- SHOPEE PATCH ----------
def extrair_video_shopee(url):
    try:
        if "br.shp.ee" in url or "shp.ee" in url:
            r = requests.head(url, allow_redirects=True, timeout=10)
            url = r.url
        if "redir=" in url:
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
        or (data.get("data", {}).get("videos", [{}])[0].get("url") if data.get("data", {}).get("videos") else None)
        or data.get("data", {}).get("path")
    )
    return video_url

# ---------- INSTAGRAM PATCH ----------
def extrair_video_instagram(url, story_id=None, index=None, ultimo=False):
    try:
        clean_url = url.split("?")[0]
        ydl_opts = {"quiet": True, "skip_download": True, "nocheckcertificate": True, "format": "best[ext=mp4]/best"}
        if COOKIES_INSTAGRAM.exists():
            ydl_opts["cookiefile"] = str(COOKIES_INSTAGRAM)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
        if info.get("url"):
            return info.get("url")
        elif info.get("requested_formats"):
            return info["requested_formats"][0].get("url")
        elif info.get("entries"):
            entries = info["entries"]
            if story_id:
                for e in entries:
                    if e.get("id") == story_id:
                        return e.get("url")
            elif index is not None and 0 <= index < len(entries):
                return entries[index].get("url")
            elif ultimo:
                return entries[-1].get("url")
            else:
                return entries[0].get("url")
        return None
    except Exception as e:
        print("Erro Instagram:", e)
        return None

# ---------- DOWNLOAD HANDLER ----------
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

    # Shopee
    if any(x in url for x in ["shopee.com", "shp.ee", "sv.shopee.com"]):
        await update.message.reply_text("🔄 Processando link da Shopee...")
        video_url = extrair_video_shopee(url)
        if not video_url:
            return await update.message.reply_text("❌ Não foi possível extrair vídeo da Shopee.")
        url = video_url

    # Instagram
    elif any(x in url for x in ["instagram.com", "instagr.am", "ig.me"]):
        await update.message.reply_text("🔄 Processando link do Instagram...")

        story_id = None
        # Detecta story_id se for link de story
        if "/stories/" in url:
            try:
                story_id = url.rstrip("/").split("/")[-1]
            except:
                pass

        # Extrai vídeo usando story_id (se houver)
        video_url = extrair_video_instagram(url, story_id=story_id)
        if not video_url:
            return await update.message.reply_text(
                "❌ Não foi possível extrair vídeo do Instagram. Pode ser privado ou cookie inválido."
            )
        url = video_url

    await update.message.reply_text("⏳ Baixando...")

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

    # Cookies
    if COOKIES_TIKTOK.exists():
        ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)
    if COOKIES_INSTAGRAM.exists():
        ydl_opts["cookiefile"] = str(COOKIES_INSTAGRAM)

    def run(url_local):
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url_local, download=True)
            return ydl.prepare_filename(info)

    loop = asyncio.get_running_loop()
    try:
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


# ---------- MAIN WEBHOOK ----------
async def main():
    verificar_pagamentos_asaas()
    app = Application.builder().token(TOKEN).build()

    await app.bot.set_my_commands([
        BotCommand("start", "Iniciar bot"),
        BotCommand("planos", "Planos premium"),
        BotCommand("duvida", "Ajuda"),
        BotCommand("meuid", "Mostrar ID"),
        BotCommand("addpremium", "Adicionar premium (admin)"),
        BotCommand("delpremium", "Remover premium (admin)"),
        BotCommand("verpremium", "Visualizar premium (admin)"),
    ])

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("planos", planos))
    app.add_handler(CommandHandler("duvida", duvida))
    app.add_handler(CommandHandler("meuid", meuid))
    app.add_handler(CommandHandler("addpremium", addpremium))
    app.add_handler(CommandHandler("delpremium", delpremium))
    app.add_handler(CommandHandler("verpremium", verpremium))
    app.add_handler(CallbackQueryHandler(callbacks_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

    asyncio.create_task(keepalive_task())

    print(f"Iniciando bot (webhook) na porta {PORT}...")
    host = os.environ.get("RENDER_EXTERNAL_HOSTNAME") or os.environ.get("RENDER_EXTERNAL_URL")
    if not host:
        print("Aviso: RENDER_EXTERNAL_HOSTNAME/URL não definido; webhook_url pode estar incorreto.")

    await app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=f"https://{host}/webhook" if host else None,
    )

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())


