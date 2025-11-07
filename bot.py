from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp, os, json, aiohttp, asyncio, traceback
from datetime import datetime, date
from flask import Flask, request
from pathlib import Path

# -----------------------------------------------------
# CONFIGURAÇÕES
# -----------------------------------------------------
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 5593153639
LIMITE_DIARIO = 10

ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"

ARQUIVO_CONTADOR = "downloads.json"
ARQUIVO_PREMIUM = "premium.json"

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

COOKIES_TIKTOK = SCRIPT_DIR / "cookies.txt"

# -----------------------------------------------------
# JSON HELPERS
# -----------------------------------------------------
def carregar_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

def salvar_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

# -----------------------------------------------------
# PREMIUM
# -----------------------------------------------------
def carregar_premium():
    data = carregar_json(ARQUIVO_PREMIUM)
    return set(map(int, data.get("premium_users", [])))

def salvar_premium(users):
    salvar_json(ARQUIVO_PREMIUM, {"premium_users": list(users)})

USUARIOS_PREMIUM = carregar_premium()
USUARIOS_PREMIUM.update({ADMIN_ID, 0, 0, 0})
salvar_premium(USUARIOS_PREMIUM)

# -----------------------------------------------------
# LIMITES
# -----------------------------------------------------
def verificar_limite(uid):
    data = carregar_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())

    if str(uid) not in data or data[str(uid)]["data"] != hoje:
        data[str(uid)] = {"data": hoje, "downloads": 0}
        salvar_json(ARQUIVO_CONTADOR, data)

    return data[str(uid)]["downloads"]

def incrementar_download(uid):
    data = carregar_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())

    if str(uid) not in data or data[str(uid)]["data"] != hoje:
        data[str(uid)] = {"data": hoje, "downloads": 1}
    else:
        data[str(uid)]["downloads"] += 1

    salvar_json(ARQUIVO_CONTADOR, data)
    return data[str(uid)]["downloads"]

# -----------------------------------------------------
# APP TELEGRAM GLOBAL
# -----------------------------------------------------
telegram_app = ApplicationBuilder().token(TOKEN).build()

# INICIALIZAÇÃO OBRIGATÓRIA (PTB20+)
asyncio.run(telegram_app.initialize())
asyncio.run(telegram_app.start())

# -----------------------------------------------------
# COMANDOS
# -----------------------------------------------------
async def start(update: Update, context):
    msg = (
        "🎬 *Bem-vindo ao Jet TikTokShop Bot!*

"
        "👉 Envie o link do vídeo para baixar.
"
        "⚠️ Free: *10 vídeos por dia*
"
        "💎 Premium: ilimitado"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

async def planos(update: Update, context):
    planos = [
        ("1 Mês", 9.90, "https://www.asaas.com/c/knu5vub6ejc2yyja"),
        ("3 Meses", 25.90, "https://www.asaas.com/c/o9pg4uxrpgwnmqzd"),
        ("1 Ano", 89.90, "https://www.asaas.com/c/puto9coszhwgprqc"),
    ]
    kb = [[InlineKeyboardButton(f"💎 {d} - R$ {v}", url=u)] for d, v, u in planos]
    await update.message.reply_text("Escolha seu plano Premium:", reply_markup=InlineKeyboardMarkup(kb))

async def duvida(update: Update, context):
    await update.message.reply_text("📞 Suporte: lavimurtha@gmail.com")

async def meuid(update: Update, context):
    await update.message.reply_text(f"🆔 Seu ID: {update.message.from_user.id}")

# -----------------------------------------------------
# DOWNLOAD
# -----------------------------------------------------
async def baixar_video(update: Update, context):
    texto = update.message.text.strip()
    uid = update.message.from_user.id

    if not texto.startswith("http"):
        return await update.message.reply_text("❌ Envie um link válido.")

    if uid not in USUARIOS_PREMIUM:
        usos = verificar_limite(uid)
        if usos >= LIMITE_DIARIO:
            return await update.message.reply_text("⚠️ Limite diário atingido. Torne-se Premium!")

    await update.message.reply_text("⏳ Baixando...")

    try:
        if "pin.it/" in texto:
            async with aiohttp.ClientSession() as s:
                async with s.get(texto, allow_redirects=True) as r:
                    texto = str(r.url)

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        outtmpl = str(DOWNLOADS_DIR / f"%(id)s-{timestamp}.%(ext)s")

        ydl_opts = {
            "outtmpl": outtmpl,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "noplaylist": True,
            "retries": 3,
            "no_warnings": True,
        }

        if COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)

        def run_ydl(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info, ydl

        loop = asyncio.get_running_loop()
        info, ydl_obj = await loop.run_in_executor(None, lambda: run_ydl(texto))

        try:
            arquivo = ydl_obj.prepare_filename(info)
        except:
            files = sorted(DOWNLOADS_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
            arquivo = str(files[0]) if files else None

        if not arquivo or not os.path.exists(arquivo):
            return await update.message.reply_text("❌ Falha ao baixar o vídeo.")

        size_mb = os.path.getsize(arquivo) / 1024 / 1024

        with open(arquivo, "rb") as f:
            if size_mb > 50:
                await update.message.reply_document(f, caption="✅ Enviado como arquivo.")
            else:
                await update.message.reply_video(f, caption="✅ Aqui está seu vídeo!")

        os.remove(arquivo)

        if uid not in USUARIOS_PREMIUM:
            usos = incrementar_download(uid)
            await update.message.reply_text(f"📊 Uso: {usos}/{LIMITE_DIARIO}")

    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")
        print(traceback.format_exc())

# -----------------------------------------------------
# ADMIN
# -----------------------------------------------------
async def premiumadd(update, context):
    if update.message.from_user.id != ADMIN_ID or not context.args:
        return
    uid = int(context.args[0])
    USUARIOS_PREMIUM.add(uid)
    salvar_premium(USUARIOS_PREMIUM)
    await update.message.reply_text(f"✅ {uid} agora é Premium")

async def premiumdel(update, context):
    if update.message.from_user.id != ADMIN_ID or not context.args:
        return
    uid = int(context.args[0])
    if uid in USUARIOS_PREMIUM:
        USUARIOS_PREMIUM.remove(uid)
        salvar_premium(USUARIOS_PREMIUM)
    await update.message.reply_text(f"🗑️ {uid} removido do Premium")

async def premiumlist(update, context):
