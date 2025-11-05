# Jet_TikTokShop Bot v4.6 - Adaptado para Render
# Downloads + Premium Dinâmico via Asaas + Ver ID + TikTok com cookies + Shopee Universal Link + fallback robusto

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, BotCommand, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp, os, json, aiohttp
from datetime import datetime, date
from pathlib import Path
import asyncio, traceback
from flask import Flask, request
import threading
import urllib.parse

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
ID_PREMIUM_FIXOS = {5593153639, 0, 0, 0}
USUARIOS_PREMIUM.update(ID_PREMIUM_FIXOS)
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
# Função para resolver links Shopee
# -----------------------
async def resolver_link_shopee(url: str) -> str:
    """Resolve links encurtados ou 'universal-link' da Shopee."""
    try:
        if "shopee.com.br/universal-link" in url and "redir=" in url:
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            redir = qs.get("redir", [None])[0]
            if redir:
                return urllib.parse.unquote(redir)

        if "sv.shopee.com.br" in url:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, allow_redirects=True) as resp:
                    return str(resp.url)

    except Exception as e:
        print(f"[Shopee resolver] erro: {e}")
    return url

# -----------------------
# Comandos do bot
# -----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensagem = (
        "🎬 *Bem-vindo(a) ao bot Jet_TikTokShop!*\n\n"
        "👉 Envie o link do vídeo que deseja baixar.\n"
        "⚠️ Usuário Free: até *10 vídeos/dia*\n"
        "💎 Premium: downloads ilimitados.\n\n"
        "✨ Use o botão de menu (📎 ➜ /) para ver os comandos disponíveis."
    )
    await update.message.reply_text(mensagem, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

async def planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    planos_disponiveis = [
        {"descricao": "1 Mês", "valor": 9.90, "url": "https://www.asaas.com/c/knu5vub6ejc2yyja"},
        {"descricao": "3 Meses", "valor": 25.90, "url": "https://www.asaas.com/c/o9pg4uxrpgwnmqzd"},
        {"descricao": "1 Ano", "valor": 89.90, "url": "https://www.asaas.com/c/puto9coszhwgprqc"}
    ]
    keyboard = [[InlineKeyboardButton(f"💎 {plano['descricao']} - R$ {plano['valor']}", url=plano['url'])] for plano in planos_disponiveis]
    markup = InlineKeyboardMarkup(keyboard)
    texto = "💎 Escolha seu plano Premium para liberar downloads ilimitados:\n\n📌 Clique no botão para pagar via PIX ou cartão."
    await update.message.reply_text(texto, reply_markup=markup)

async def duvida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Contato: lavimurtha@gmail.com", parse_mode="Markdown")

async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    await update.message.reply_text(f"🆔 Seu Telegram ID é: `{user_id}`", parse_mode="Markdown")

# -----------------------
# Download de vídeo com fallback robusto
# -----------------------
async def baixar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        # Resolver Shopee
        if "shopee.com.br" in texto:
            texto = await resolver_link_shopee(texto)

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
            "ignoreerrors": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "retries": 3,
            "no_warnings": True,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
            }
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

        # Fallback robusto para localizar arquivo
        candidato = None
        try:
            candidato = ydl_obj.prepare_filename(info)
        except Exception:
            pass

        if not candidato or not os.path.exists(candidato):
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
# Comandos Admin
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
    lista = "\n".join(f"• {uid}" for uid in USUARIOS_PREMIUM)
    await update.message.reply_text(f"💎 Usuários Premium:\n{lista}")

# -----------------------
# Webhook Flask
# -----------------------
flask_app = Flask(__name__)

@flask_app.route("/health", methods=["GET"])
def health():
    return "OK", 200

@flask_app.route("/webhook_asaas", methods=["POST"])
def webhook_asaas():
    data = request.json
    status = data.get("status")
    telegram_id = int(data.get("metadata", {}).get("telegram_id", 0))

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

@flask_app.route("/webhook_telegram", methods=["POST"])
def webhook_telegram():
    from telegram import Update
    update = Update.de_json(request.get_json(force=True), app.bot)
    app.update_queue.put(update)
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)

# -----------------------
# Inicialização
# -----------------------
def main():
    threading.Thread(target=run_flask, daemon=True).start()

    async def comandos_post_init(app):
        await app.bot.set_my_commands([
            BotCommand("start", "Iniciar o bot"),
            BotCommand("planos", "Ver planos Premium"),
            BotCommand("duvida", "Ajuda e contato"),
            BotCommand("meuid", "Ver seu ID do Telegram")
        ])

    global app
    app = ApplicationBuilder().token(TOKEN).post_init(comandos_post_init).build()

    # Comandos principais
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("planos", planos))
    app.add_handler(CommandHandler("duvida", duvida))
    app.add_handler(CommandHandler("meuid", meuid))

    # Admin
    app.add_handler(CommandHandler("premiumadd", premiumadd))
    app.add_handler(CommandHandler("premiumdel", premiumdel))
    app.add_handler(CommandHandler("premiumlist", premiumlist))

    # Mensagens de links
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

    print("🤖 Bot iniciado... aguardando mensagens.")
    app.run_polling()

if __name__ == "__main__":
    main()
