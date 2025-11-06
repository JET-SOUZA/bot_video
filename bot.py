# Bot convertido para Webhook (Render) - Jet_TikTokShop
# Esta versão remove TODA lógica de polling e usa SOMENTE WEBHOOK

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp, os, json, aiohttp
from datetime import datetime, date
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
# Funções JSON
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
    return set(map(int, dados.get("premium_users", [])))


def salvar_premium(usuarios):
    salvar_json(ARQUIVO_PREMIUM, {"premium_users": list(usuarios)})


USUARIOS_PREMIUM = carregar_premium()

# IDs Premium fixos
ID_PREMIUM_1 = 5593153639
ID_PREMIUM_2 = 0
ID_PREMIUM_3 = 0
ID_PREMIUM_4 = 0

USUARIOS_PREMIUM.update({ID_PREMIUM_1, ID_PREMIUM_2, ID_PREMIUM_3, ID_PREMIUM_4})
salvar_premium(USUARIOS_PREMIUM)

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
# Comandos do BOT
# -----------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensagem = (
        "🎬 *Bem-vindo(a) ao bot Jet_TikTokShop!*\n\n"
        "👉 Envie o link do vídeo que deseja baixar.\n"
        "⚠️ Usuário Free: até *10 vídeos/dia*\n"
        "💎 Premium: downloads ilimitados.\n\n"
        "✨ Use o menu (📎 ➜ /) para comandos."
    )
    await update.message.reply_text(mensagem, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())


async def planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    planos_disponiveis = [
        {"descricao": "1 Mês", "valor": 9.90, "url": "https://www.asaas.com/c/knu5vub6ejc2yyja"},
        {"descricao": "3 Meses", "valor": 25.90, "url": "https://www.asaas.com/c/o9pg4uxrpgwnmqzd"},
        {"descricao": "1 Ano", "valor": 89.90, "url": "https://www.asaas.com/c/puto9coszhwgprqc"}
    ]

    keyboard = [[InlineKeyboardButton(f"💎 {p['descricao']} - R$ {p['valor']}", url=p['url'])] for p in planos_disponiveis]
    markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "💎 Escolha seu plano Premium:\nClique no botão para pagar via PIX ou cartão.",
        reply_markup=markup
    )


async def duvida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Contato: lavimurtha@gmail.com")


async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    await update.message.reply_text(f"🆔 Seu ID: {uid}")

# -----------------------
# Download
# -----------------------

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
                await update.message.reply_document(f, caption="✅ Vídeo (enviado como documento)")
            else:
                await update.message.reply_video(f, caption="✅ Vídeo em alta qualidade!")

        os.remove(arquivo)

        if user_id not in USUARIOS_PREMIUM:
            novos = incrementar_download(user_id)
            await update.message.reply_text(f"📊 Uso diário: {novos}/{LIMITE_DIARIO}")

    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")
        print(traceback.format_exc())

# -----------------------
# Admin
# -----------------------

async def premiumadd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    if not context.args:
        return
    uid = int(context.args[0])
    USUARIOS_PREMIUM.add(uid)
    salvar_premium(USUARIOS_PREMIUM)
    await update.message.reply_text(f"✅ {uid} virou Premium")


async def premiumdel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    if not context.args:
        return
    uid = int(context.args[0])
    if uid in USUARIOS_PREMIUM:
        USUARIOS_PREMIUM.remove(uid)
        salvar_premium(USUARIOS_PREMIUM)
    await update.message.reply_text(f"🗑️ {uid} removido")


async def premiumlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    lista = "\n".join(str(x) for x in USUARIOS_PREMIUM)
    await update.message.reply_text(f"💎 Premium:\n{lista}")

# -----------------------
# Flask Webhook
# -----------------------

flask_app = Flask(__name__)


@flask_app.route("/health", methods=["GET"])
def health():
    return "OK", 200


@flask_app.route("/webhook_asaas", methods=["POST"])
def webhook_asaas():
    data = request.json
    status = data.get("status")
    telegram_id = int(data.get("metadata",{}).get("telegram_id",0))

    if telegram_id == 0:
        return "NO ID", 400

    if status == "CONFIRMED":
        USUARIOS_PREMIUM.add(telegram_id)
        salvar_premium(USUARIOS_PREMIUM)
    elif status in ["CANCELED", "EXPIRED"]:
        if telegram_id in USUARIOS_PREMIUM:
            USUARIOS_PREMIUM.remove(telegram_id)
            salvar_premium(USUARIOS_PREMIUM)

    return "OK", 200


@flask_app.route("/webhook_telegram", methods=["POST"])
def webhook_telegram():
    update = Update.de_json(request.get_json(force=True), app.bot)
    app.update_queue.put(update)
    return "OK", 200

# -----------------------
# INICIALIZAÇÃO (WEBHOOK)
# -----------------------

def main():
    global app

    async def comandos_post_init(app):
        await app.bot.set_my_commands([
            BotCommand("start", "Iniciar"),
            BotCommand("planos", "Planos Premium"),
            BotCommand("duvida", "Ajuda"),
            BotCommand("meuid", "Seu ID"),
        ])

    app = ApplicationBuilder().token(TOKEN).post_init(comandos_post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("planos", planos))
    app.add_handler(CommandHandler("duvida", duvida))
    app.add_handler(CommandHandler("meuid", meuid))

    app.add_handler(CommandHandler("premiumadd", premiumadd))
    app.add_handler(CommandHandler("premiumdel", premiumdel))
    app.add_handler(CommandHandler("premiumlist", premiumlist))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

    threading.Thread(target=lambda: flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000))), daemon=True).start()

    # ✅ MODO WEBHOOK (SEM POLLING)
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        webhook_url=os.environ.get("WEBHOOK_URL")
    )


if __name__ == "__main__":
    main()
