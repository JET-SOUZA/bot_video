# Jet_TikTokShop Bot v5.0 - Webhook Render (Flask + PTB20)
# Downloads + Premium Asaas + Limite Diário + TikTok cookies
# Compatível com Render (sem polling) – domínio confirmado: bot-video-mgli.onrender.com

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp, os, json, aiohttp
from datetime import datetime, date
from pathlib import Path
import asyncio, traceback, threading

from flask import Flask, request

# -----------------------
# Configurações
# -----------------------
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Defina a variável de ambiente BOT_TOKEN no Render.")

BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://bot-video-mgli.onrender.com")  # pode sobrescrever em env
ADMIN_ID = 5593153639
LIMITE_DIARIO = 10

ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")  # opcional (usamos só para webhook por enquanto)
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
# Util JSON
# -----------------------
def carregar_json(caminho):
    if os.path.exists(caminho):
        try:
            with open(caminho, "r") as f:
                return json.load(f)
        except Exception:
            return {}
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
    if str(user_id) not in dados or dados[str(user_id)].get("data") != hoje:
        dados[str(user_id)] = {"data": hoje, "downloads": 0}
        salvar_json(ARQUIVO_CONTADOR, dados)
    return dados[str(user_id)]["downloads"]

def incrementar_download(user_id):
    dados = carregar_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())
    if str(user_id) not in dados or dados[str(user_id)].get("data") != hoje:
        dados[str(user_id)] = {"data": hoje, "downloads": 1}
    else:
        dados[str(user_id)]["downloads"] += 1
    salvar_json(ARQUIVO_CONTADOR, dados)
    return dados[str(user_id)]["downloads"]

# -----------------------
# Handlers do bot
# -----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensagem = (
        "🎬 *Bem-vindo(a) ao bot Jet_TikTokShop!*\n\n"
        "👉 Envie o link do vídeo que deseja baixar.\n"
        f"⚠️ Usuário Free: até *{LIMITE_DIARIO} vídeos/dia*\n"
        "💎 Premium: downloads ilimitados.\n\n"
        "✨ Use o botão de menu (📎 ➜ /) para ver os comandos disponíveis."
    )
    await update.message.reply_text(mensagem, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

async def planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    planos_disponiveis = [
        {"descricao": "1 Mês", "valor": 9.90, "url": "https://www.asaas.com/c/knu5vub6ejc2yyja"},
        {"descricao": "3 Meses", "valor": 25.90, "url": "https://www.asaas.com/c/o9pg4uxrpgwnmqzd"},
        {"descricao": "1 Ano", "valor": 89.90, "url": "https://www.asaas.com/c/puto9coszhwgprqc"},
    ]
    keyboard = [[InlineKeyboardButton(f"💎 {p['descricao']} - R$ {p['valor']}", url=p['url'])] for p in planos_disponiveis]
    await update.message.reply_text(
        "💎 Escolha seu plano Premium para liberar downloads ilimitados:\n\n"
        "📌 Clique no botão para pagar via PIX ou cartão.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def duvida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Contato: lavimurtha@gmail.com", parse_mode="Markdown")

async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    await update.message.reply_text(f"🆔 Seu Telegram ID é: `{user_id}`", parse_mode="Markdown")

# -----------------------
# Download de vídeo
# -----------------------
async def baixar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    texto = update.message.text.strip()
    user_id = update.message.from_user.id

    if not texto.startswith("http"):
        await update.message.reply_text("❌ Envie um link válido de vídeo.")
        return

    if user_id not in USUARIOS_PREMIUM:
        usados = verificar_limite(user_id)
        if usados >= LIMITE_DIARIO:
            await update.message.reply_text("⚠️ Você atingiu seu limite diário de downloads. Assine o Premium para uso ilimitado!")
            return

    await update.message.reply_text("⏳ Preparando download...", parse_mode="Markdown")

    try:
        # Resolver encurtadores/redirects (Pinterest, Shopee etc.)
        if any(dom in texto for dom in ["pin.it/", "shopee.com", "sv.shopee.com", "universal-link?"]):
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
            "ignoreerrors": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "retries": 3,
            "no_warnings": True,
        }

        if COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)
        if "CHROME_BIN" in os.environ:
            ydl_opts["browser_executable"] = os.environ["CHROME_BIN"]

        def run_ydl(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info, ydl

        loop = asyncio.get_running_loop()
        info, ydl_obj = await loop.run_in_executor(None, lambda: run_ydl(texto))

        try:
            candidato = ydl_obj.prepare_filename(info)
        except Exception:
            arquivos = sorted(DOWNLOADS_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
            candidato = str(arquivos[0]) if arquivos else None

        if not candidato or not os.path.exists(candidato):
            await update.message.reply_text("⚠️ Não foi possível localizar o arquivo baixado.")
            return

        tamanho_mb = os.path.getsize(candidato) / 1024 / 1024
        with open(candidato, "rb") as f:
            if tamanho_mb > 50:
                await update.message.reply_document(f, caption="✅ Aqui está seu vídeo (documento).")
            else:
                await update.message.reply_video(f, caption="✅ Aqui está seu vídeo em alta qualidade!")

        os.remove(candidato)

        if user_id not in USUARIOS_PREMIUM:
            novos_usos = incrementar_download(user_id)
            await update.message.reply_text(f"📊 Uso diário: *{novos_usos}/{LIMITE_DIARIO}*", parse_mode="Markdown")

    except Exception as e:
        tb = traceback.format_exc()
        await update.message.reply_text(f"❌ Erro ao baixar: {e}")
        print(tb)

# -----------------------
# Admin
# -----------------------
async def premiumadd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID or not context.args:
        return
    user_id = int(context.args[0])
    USUARIOS_PREMIUM.add(user_id)
    salvar_premium(USUARIOS_PREMIUM)
    await update.message.reply_text(f"✅ Usuário {user_id} adicionado como Premium.")

async def premiumdel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID or not context.args:
        return
    user_id = int(context.args[0])
    if user_id in USUARIOS_PREMIUM:
        USUARIOS_PREMIUM.remove(user_id)
        salvar_premium(USUARIOS_PREMIUM)
        await update.message.reply_text(f"🗑️ Usuário {user_id} removido do Premium.")

async def premiumlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    lista = "\n".join(f"• {uid}" for uid in sorted(USUARIOS_PREMIUM))
    await update.message.reply_text(f"💎 Usuários Premium:\n{lista or '— vazio —'}")

# -----------------------
# App Telegram (PTB) – inicialização assíncrona
# -----------------------
tg_app = None  # Application (PTB)
tg_loop = None # event loop do PTB em thread separada

async def _build_and_start_tg_app():
    global tg_app
    tg_app = ApplicationBuilder().token(TOKEN).build()

    # Comandos principais
    tg_app.add_handler(CommandHandler("start", start))
    tg_app.add_handler(CommandHandler("planos", planos))
    tg_app.add_handler(CommandHandler("duvida", duvida))
    tg_app.add_handler(CommandHandler("meuid", meuid))

    # Admin
    tg_app.add_handler(CommandHandler("premiumadd", premiumadd))
    tg_app.add_handler(CommandHandler("premiumdel", premiumdel))
    tg_app.add_handler(CommandHandler("premiumlist", premiumlist))

    # Mensagens de links
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

    await tg_app.initialize()
    await tg_app.bot.set_my_commands([
        BotCommand("start", "Iniciar o bot"),
        BotCommand("planos", "Ver planos Premium"),
        BotCommand("duvida", "Ajuda e contato"),
        BotCommand("meuid", "Ver seu ID do Telegram"),
    ])

    # Garante que não há webhook antigo e define o novo
    await tg_app.bot.delete_webhook(drop_pending_updates=True)
    await tg_app.bot.set_webhook(url=f"{BASE_URL}/{TOKEN}")

    await tg_app.start()  # inicia processamento da fila update_queue
    # NÃO chamamos .run_* nem .updater/polling

def start_tg_thread():
    """Sobe um loop asyncio dedicado para o PTB em thread separada."""
    def runner():
        global tg_loop
        tg_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(tg_loop)
        tg_loop.run_until_complete(_build_and_start_tg_app())
        tg_loop.run_forever()

    t = threading.Thread(target=runner, daemon=True)
    t.start()

# -----------------------
# Flask (HTTP) – endpoints
# -----------------------
flask_app = Flask(__name__)

@flask_app.get("/health")
def health():
    return "OK", 200

@flask_app.post("/webhook_asaas")
def webhook_asaas():
    data = request.json or {}
    status = data.get("status")
    telegram_id = int((data.get("metadata") or {}).get("telegram_id") or 0)

    if telegram_id == 0:
        return "No telegram ID", 400

    if status == "CONFIRMED":
        USUARIOS_PREMIUM.add(telegram_id)
        salvar_premium(USUARIOS_PREMIUM)
    elif status in ["CANCELED", "EXPIRED"]:
        if telegram_id in USUARIOS_PREMIUM:
            USUARIOS_PREMIUM.remove(telegram_id)
            salvar_premium(USUARIOS_PREMIUM)

    return "OK", 200

@flask_app.post(f"/{TOKEN}")
def webhook_telegram():
    # Recebe update do Telegram e joga na fila do PTB
    if tg_app is None:
        return "App not ready", 503
    try:
        update = Update.de_json(request.get_json(force=True), tg_app.bot)
        tg_app.update_queue.put_nowait(update)
    except Exception as e:
        print("Erro no webhook_telegram:", e)
        return "Bad Request", 400
    return "OK", 200

# -----------------------
# Entry point Render / Gunicorn
# -----------------------
def create_app():
    """
    Ponto de entrada para Gunicorn: gunicorn 'bot:create_app()'
    Sobe thread do PTB e devolve a app Flask.
    """
    # Sobe o Telegram (PTB) em thread separada UMA ÚNICA VEZ
    start_tg_thread()
    return flask_app

# Execução local (opcional)
if __name__ == "__main__":
    start_tg_thread()
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)
