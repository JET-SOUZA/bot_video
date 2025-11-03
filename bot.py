# Jet_TikTokShop Bot v4.5 - Adaptado para Render com Webhooks
# Downloads + Premium Dinâmico via Asaas + Ver ID + TikTok/Instagram + Admin tools

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp, os, json, aiohttp
from datetime import datetime, date, timedelta
from pathlib import Path
import asyncio, traceback
from flask import Flask, request
import threading

# -----------------------
# Configurações
# -----------------------
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

# -----------------------
# JSON helpers
# -----------------------
def carregar_json(caminho):
    if os.path.exists(caminho):
        with open(caminho, "r") as f:
            return json.load(f)
    return {}

def salvar_json(caminho, dados):
    with open(caminho, "w") as f:
        json.dump(dados, f)

# -----------------------
# Premium
# -----------------------
def carregar_premium():
    dados = carregar_json(ARQUIVO_PREMIUM)
    return dados if isinstance(dados, dict) else {}

def salvar_premium(dados):
    salvar_json(ARQUIVO_PREMIUM, dados)

USUARIOS_PREMIUM = carregar_premium()
USUARIOS_PREMIUM.setdefault(str(ADMIN_ID), {"validade": "2099-12-31"})
salvar_premium(USUARIOS_PREMIUM)

def is_premium(user_id):
    info = USUARIOS_PREMIUM.get(str(user_id))
    if not info: return False
    try:
        validade = datetime.strptime(info["validade"], "%Y-%m-%d").date()
    except Exception:
        return False
    return validade >= date.today()

def registrar_validade(user_id, descricao):
    descricao_norm = (descricao or "").strip().lower()
    dias = 30
    if "1 mês" in descricao_norm or "1 mes" in descricao_norm: dias = 30
    elif "3 meses" in descricao_norm or "3 mes" in descricao_norm: dias = 90
    elif "1 ano" in descricao_norm or "1 ano" in descricao_norm: dias = 365
    validade = date.today() + timedelta(days=dias)
    USUARIOS_PREMIUM[str(user_id)] = {"validade": validade.strftime("%Y-%m-%d")}
    salvar_premium(USUARIOS_PREMIUM)
    print(f"[premium] {user_id} -> validade {validade.isoformat()}")

# -----------------------
# Limite diário
# -----------------------
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

# -----------------------
# Comandos
# -----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *Bem-vindo(a) ao bot Jet_TikTokShop!*\n\n"
        "👉 Envie o link do vídeo que deseja baixar.\n"
        "⚠️ Free: até *10 vídeos/dia*\n"
        "💎 Premium: downloads ilimitados.\n\n"
        "✨ Use o menu (📎 ➜ /) para ver os comandos.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

async def planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    planos_disponiveis = [
        {"descricao": "1 Mês", "valor": 9.90, "url": "https://www.asaas.com/c/knu5vub6ejc2yyja"},
        {"descricao": "3 Meses", "valor": 25.90, "url": "https://www.asaas.com/c/o9pg4uxrpgwnmqzd"},
        {"descricao": "1 Ano", "valor": 89.90, "url": "https://www.asaas.com/c/puto9coszhwgprqc"}
    ]
    keyboard = [[InlineKeyboardButton(f"💎 {p['descricao']} - R$ {p['valor']}", url=p['url'])] for p in planos_disponiveis]
    await update.message.reply_text("💎 Escolha seu plano Premium:", reply_markup=InlineKeyboardMarkup(keyboard))

async def duvida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Contato: lavimurtha@gmail.com", parse_mode="Markdown")

async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Seu Telegram ID é: `{update.message.from_user.id}`", parse_mode="Markdown")

# -----------------------
# Download de vídeo/foto
# -----------------------
async def baixar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    user_id = update.message.from_user.id
    if not texto.startswith("http"):
        await update.message.reply_text("❌ Envie um link válido.")
        return

    if not is_premium(user_id):
        usados = verificar_limite(user_id)
        if usados >= LIMITE_DIARIO:
            await update.message.reply_text("⚠️ Limite diário atingido. Assine Premium!")
            return

    await update.message.reply_text("⏳ Baixando...")

    try:
        if "pin.it/" in texto:
            async with aiohttp.ClientSession() as s:
                async with s.get(texto, allow_redirects=True) as r:
                    texto = str(r.url)

        out_template = str(DOWNLOADS_DIR / f"%(id)s-%(title)s.%(ext)s")
        ydl_opts = {"outtmpl": out_template, "format": "best", "quiet": True}
        if COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)

        def run_ydl(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info, ydl

        loop = asyncio.get_running_loop()
        info, ydl_obj = await loop.run_in_executor(None, lambda: run_ydl(texto))
        file_path = ydl_obj.prepare_filename(info)

        # envia foto ou vídeo automaticamente
        if file_path.lower().endswith((".jpg", ".png", ".jpeg")):
            with open(file_path, "rb") as f:
                await update.message.reply_photo(f, caption="✅ Aqui está sua foto!")
        else:
            with open(file_path, "rb") as f:
                await update.message.reply_video(f, caption="✅ Aqui está seu vídeo!")

        os.remove(file_path)
        if not is_premium(user_id):
            incrementar_download(user_id)

    except Exception as e:
        await update.message.reply_text(f"Erro: {e}")

# -----------------------
# Admin
# -----------------------
async def premiumlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID: return
    texto = "\n".join([f"• {uid} (até {info.get('validade')})" for uid, info in USUARIOS_PREMIUM.items()])
    await update.message.reply_text("💎 Usuários Premium:\n" + texto)

async def addpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Você não tem permissão para usar este comando.")
        return
    try:
        telegram_id = str(context.args[0])
        dias = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("Uso correto: /addpremium <id> <dias>")
        return
    validade = (date.today() + timedelta(days=dias)).strftime("%Y-%m-%d")
    USUARIOS_PREMIUM[telegram_id] = {"validade": validade}
    salvar_premium(USUARIOS_PREMIUM)
    await update.message.reply_text(f"✅ Usuário `{telegram_id}` recebeu premium até {validade}.", parse_mode="Markdown")

async def delpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Você não tem permissão para usar este comando.")
        return
    try:
        telegram_id = str(context.args[0])
    except IndexError:
        await update.message.reply_text("Uso correto: /delpremium <id>")
        return
    if telegram_id in USUARIOS_PREMIUM:
        USUARIOS_PREMIUM.pop(telegram_id, None)
        salvar_premium(USUARIOS_PREMIUM)
        await update.message.reply_text(f"❌ Usuário `{telegram_id}` removido do premium.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Usuário não encontrado.")

# -----------------------
# Flask webhook
# -----------------------
flask_app = Flask(__name__)

@flask_app.route("/webhook_telegram", methods=["POST"])
def telegram_webhook():
    data = request.get_json(force=True)
    asyncio.run_coroutine_threadsafe(
        application.update_queue.put(Update.de_json(data, application.bot)),
        asyncio.get_event_loop()
    )
    return "OK"

# -----------------------
# Iniciar bot
# -----------------------
application = ApplicationBuilder().token(TOKEN).build()

# Handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("planos", planos))
application.add_handler(CommandHandler("duvida", duvida))
application.add_handler(CommandHandler("meuid", meuid))
application.add_handler(CommandHandler("premiumlist", premiumlist))
application.add_handler(CommandHandler("addpremium", addpremium))
application.add_handler(CommandHandler("delpremium", delpremium))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

# -----------------------
# Run Flask in Thread
# -----------------------
def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

threading.Thread(target=run_flask).start()
print("[bot] Bot iniciado via webhook. Acesse: /start")
