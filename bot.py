# Bot completo atualizado para Webhook (Render) — Jet_TikTokShop
# Inclui correção do webhook (process_update), sem polling

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp, os, json, aiohttp
from datetime import datetime, date
from pathlib import Path
import asyncio, traceback
from flask import Flask, request
import threading

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

if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    with open(COOKIES_TIKTOK, "w") as f:
        f.write(os.environ["COOKIES_TIKTOK"])

# -----------------------------
# JSON HELPERS
# -----------------------------

def carregar_json(caminho):
    if os.path.exists(caminho):
        with open(caminho, "r") as f:
            return json.load(f)
    return {}


def salvar_json(caminho, dados):
    with open(caminho, "w") as f:
        json.dump(dados, f)

# -----------------------------
# PREMIUM SYSTEM
# -----------------------------

def carregar_premium():
    dados = carregar_json(ARQUIVO_PREMIUM)
    return set(map(int, dados.get("premium_users", [])))


def salvar_premium(usuarios):
    salvar_json(ARQUIVO_PREMIUM, {"premium_users": list(usuarios)})


USUARIOS_PREMIUM = carregar_premium()

ID_PREMIUM_1 = 5593153639
ID_PREMIUM_2 = 0
ID_PREMIUM_3 = 0
ID_PREMIUM_4 = 0

USUARIOS_PREMIUM.update({ID_PREMIUM_1, ID_PREMIUM_2, ID_PREMIUM_3, ID_PREMIUM_4})
salvar_premium(USUARIOS_PREMIUM)

# -----------------------------
# LIMITES DIÁRIOS
# -----------------------------

def verificar_limite(user_id):
    dados = carregar_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())
    if str(user_id) not in dados or dados[str(user_id)]["data"] != hoje:
        dados[str(user_id)] = {"data": hoje, "downloads": 0}
        salvar_json(ARQUIVO_CONTADOR, dados)
    return dados[str(user_id)]["downloads"]


def incrementar_download(user_id):
    dados = carregar_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())
    if str(user_id) not in dados or dados[str(user_id)]["data"] != hoje:
        dados[str(user_id)] = {"data": hoje, "downloads": 1}
    else:
        dados[str(user_id)]["downloads"] += 1
    salvar_json(ARQUIVO_CONTADOR, dados)
    return dados[str(user_id)]["downloads"]

# -----------------------------
# COMANDOS DO BOT
# -----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🎬 *Bem-vindo(a) ao Jet TikTokShop Bot!*

"
        "👉 Envie o link do vídeo que deseja baixar.
"
        "⚠️ Free: até *10 vídeos/dia*
"
        "💎 Premium: downloads ilimitados."
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())


async def planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    planos_list = [
        {"descricao": "1 Mês", "valor": 9.90, "url": "https://www.asaas.com/c/knu5vub6ejc2yyja"},
        {"descricao": "3 Meses", "valor": 25.90, "url": "https://www.asaas.com/c/o9pg4uxrpgwnmqzd"},
        {"descricao": "1 Ano", "valor": 89.90, "url": "https://www.asaas.com/c/puto9coszhwgprqc"}
    ]

    buttons = [[InlineKeyboardButton(f"💎 {p['descricao']} - R$ {p['valor']}", url=p['url'])] for p in planos_list]
    await update.message.reply_text("Selecione seu plano Premium:", reply_markup=InlineKeyboardMarkup(buttons))


async def duvida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Contato: lavimurtha@gmail.com")


async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Seu ID: {update.message.from_user.id}")

# -----------------------------
# SISTEMA DE DOWNLOAD
# -----------------------------

async def baixar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    user_id = update.message.from_user.id

    if not texto.startswith("http"):
        return await update.message.reply_text("❌ Envie um link válido.")

    if user_id not in USUARIOS_PREMIUM:
        usados = verificar_limite(user_id)
        if usados >= LIMITE_DIARIO:
            return await update.message.reply_text("⚠️ Limite diário atingido. Assine Premium!")

    await update.message.reply_text("⏳ Baixando...")

    try:
        if "pin.it/" in texto:
            async with aiohttp.ClientSession() as session:
                async with session.get(texto, allow_redirects=True) as resp:
                    texto = str(resp.url)

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        out_template = str(DOWNLOADS_DIR / f"%(id)s-{timestamp}.%(ext)s")

        ydl_opts = {
            "outtmpl": out_template,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "noplaylist": True,
            "nocheckcertificate": True,
            "retries": 3,
            "no_warnings": True
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
            arquivos = sorted(DOWNLOADS_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
            arquivo = str(arquivos[0]) if arquivos else None

        if not arquivo or not os.path.exists(arquivo):
            return await update.message.reply_text("⚠️ Falha ao localizar vídeo.")

        tam = os.path.getsize(arquivo) / 1024 / 1024

        with open(arquivo, "rb") as f:
            if tam > 50:
                await update.message.reply_document(f, caption="✅ Enviado como documento.")
            else:
                await update.message.reply_video(f, caption="✅ Aqui está seu vídeo!")

        os.remove(arquivo)

        if user_id not in USUARIOS_PREMIUM:
            novos = incrementar_download(user_id)
            await update.message.reply_text(f"📊 Uso: {novos}/{LIMITE_DIARIO}")

    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")
        print(traceback.format_exc())

# -----------------------------
# ADMIN
# -----------------------------

async def premiumadd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID or not context.args:
        return
    uid = int(context.args[0])
    USUARIOS_PREMIUM.add(uid)
    salvar_premium(USUARIOS_PREMIUM)
    await update.message.reply_text(f"✅ {uid} virou Premium")


async def premiumdel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID or not context.args:
        return
    uid = int(context.args[0])
    if uid in USUARIOS_PREMIUM:
