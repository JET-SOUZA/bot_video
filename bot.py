# Jet_TikTokShop Bot v4.6 - Adaptado para Render com suporte YouTube
# Downloads + Premium Dinâmico via Asaas + Ver ID + TikTok/Instagram/YouTube com cookies + Validade automática + Admin tools

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp, os, json, aiohttp
from datetime import datetime, date, timedelta
from pathlib import Path
import asyncio, threading
from flask import Flask, request

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

# Cookies TikTok
COOKIES_TIKTOK = SCRIPT_DIR / "cookies.txt"
if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    with open(COOKIES_TIKTOK, "w") as f:
        f.write(os.environ["COOKIES_TIKTOK"])

# Cookies Instagram
COOKIES_INSTAGRAM = SCRIPT_DIR / "cookies_instagram.txt"
if "COOKIES_INSTAGRAM" in os.environ:
    conteudo = os.environ["COOKIES_INSTAGRAM"].replace("\\n", "\n")
    with open(COOKIES_INSTAGRAM, "w", encoding="utf-8") as f:
        f.write(conteudo)

# Cookies YouTube
COOKIES_YOUTUBE = SCRIPT_DIR / "cookies_youtube.txt"
if "COOKIES_YOUTUBE" in os.environ and not COOKIES_YOUTUBE.exists():
    with open(COOKIES_YOUTUBE, "w") as f:
        f.write(os.environ["COOKIES_YOUTUBE"])

# -----------------------
# Funções JSON gerais
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
    if not isinstance(dados, dict):
        dados = {}
    return dados

def salvar_premium(dados):
    salvar_json(ARQUIVO_PREMIUM, dados)

USUARIOS_PREMIUM = carregar_premium()
USUARIOS_PREMIUM.setdefault(str(ADMIN_ID), {"validade": "2099-12-31"})
salvar_premium(USUARIOS_PREMIUM)

def is_premium(user_id):
    info = USUARIOS_PREMIUM.get(str(user_id))
    if not info:
        return False
    try:
        validade = datetime.strptime(info["validade"], "%Y-%m-%d").date()
    except Exception:
        return False
    return validade >= date.today()

# -----------------------
# Registrar validade
# -----------------------
def registrar_validade(user_id, descricao):
    descricao_norm = (descricao or "").strip().lower()
    if "1 mês" in descricao_norm or "1 mes" in descricao_norm:
        dias = 30
    elif "3 meses" in descricao_norm or "3 mes" in descricao_norm:
        dias = 90
    elif "1 ano" in descricao_norm or "1 ano" in descricao_norm:
        dias = 365
    else:
        dias = 30
    validade = date.today() + timedelta(days=dias)
    USUARIOS_PREMIUM[str(user_id)] = {"validade": validade.strftime("%Y-%m-%d")}
    salvar_premium(USUARIOS_PREMIUM)
    print(f"[premium] {user_id} -> validade {validade.isoformat()}")

# -----------------------
# Notificações automáticas
# -----------------------
async def verificar_vencimentos(app):
    while True:
        hoje = date.today()
        for user_id, info in list(USUARIOS_PREMIUM.items()):
            try:
                validade = datetime.strptime(info["validade"], "%Y-%m-%d").date()
            except Exception:
                continue
            dias_restantes = (validade - hoje).days
            try:
                if dias_restantes == 1:
                    await app.bot.send_message(chat_id=int(user_id),
                        text="⚠️ *Seu plano Premium vence amanhã!* Renove para continuar com downloads ilimitados.",
                        parse_mode="Markdown")
                elif dias_restantes == 0:
                    await app.bot.send_message(chat_id=int(user_id),
                        text="💔 *Seu plano Premium vence hoje!* Renove para não perder o acesso.",
                        parse_mode="Markdown")
                elif dias_restantes < 0:
                    await app.bot.send_message(chat_id=int(user_id),
                        text="❌ Seu plano Premium expirou. Torne-se Premium novamente acessando /planos.")
                    USUARIOS_PREMIUM.pop(user_id, None)
                    salvar_premium(USUARIOS_PREMIUM)
            except Exception as e:
                print(f"[verificar_vencimentos] erro notificando {user_id}: {e}")
        await asyncio.sleep(86400)

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
# Comandos do bot
# -----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensagem = (
        "🎬 *Bem-vindo(a) ao bot Jet_TikTokShop!*\n\n"
        "👉 Envie o link do vídeo que deseja baixar.\n"
        "⚠️ Usuário Free: até *10 vídeos/dia*\n"
        "💎 Premium: downloads ilimitados.\n\n"
        "✨ Use o menu (📎 ➜ /) para ver os comandos."
    )
    await update.message.reply_text(mensagem, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

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
# Download de vídeo
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

        # Configuração yt-dlp com cookies
        ydl_opts = {"outtmpl": out_template, "format": "best", "quiet": True}

        if "instagram.com" in texto and COOKIES_INSTAGRAM.exists():
            ydl_opts["cookiefile"] = str(COOKIES_INSTAGRAM)
        elif "tiktok.com" in texto and COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)
        elif "youtube.com" in texto and COOKIES_YOUTUBE.exists():
            ydl_opts["cookiefile"] = str(COOKIES_YOUTUBE)
            ydl_opts["extractor_args"] = {"youtubetab": {"skip": "authcheck"}}

        def run_ydl(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info, ydl

        loop = asyncio.get_running_loop()
        info, ydl_obj = await loop.run_in_executor(None, lambda: run_ydl(texto))
        file_path = ydl_obj.prepare_filename(info)

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
    if update.message.from_user.id != ADMIN_ID:
        return
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
    await update.message.reply_text(f"✅ Usuário `{telegram_id}` recebeu acesso premium até {validade}.", parse_mode="Markdown")

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
        await update.message.reply_text(f"⚠️ Usuário `{telegram_id}` não encontrado no premium.", parse_mode="Markdown")

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
    telegram_id = int(data.get("metadata", {}).get("telegram_id", 0))
    descricao = data.get("description", "")
    if telegram_id == 0:
        return "No telegram ID", 400

    if status == "CONFIRMED":
        registrar_validade(telegram_id, descricao)
        salvar_premium(USUARIOS_PREMIUM)
        try:
            validade = USUARIOS_PREMIUM.get(str(telegram_id), {}).get("validade")
            texto = (
                "💎 *Seu plano Premium foi ativado com sucesso!*\n\n"
                f"✅ Validade até: *{datetime.strptime(validade, '%Y-%m-%d').strftime('%d/%m/%Y')}*\n\n"
                "Aproveite seus downloads ilimitados! 🚀"
            )
            asyncio.run(app.bot.send_message(chat_id=telegram_id, text=texto, parse_mode="Markdown"))
        except Exception as e:
            print(f"[webhook_asaas] erro ao notificar usuario {telegram_id}: {e}")
        try:
            texto_admin = (
                f"📢 Novo Premium confirmado:\nID: {telegram_id}\nPlano: {descricao or 'não informado'}\n"
                f"Validade: {USUARIOS_PREMIUM.get(str(telegram_id), {}).get('validade')}"
            )
            asyncio.run(app.bot.send_message(chat_id=ADMIN_ID, text=texto_admin))
        except Exception as e:
            print(f"[webhook_asaas] erro ao notificar admin: {e}")
    elif status in ["CANCELED", "EXPIRED"]:
        USUARIOS_PREMIUM.pop(str(telegram_id), None)
        salvar_premium(USUARIOS_PREMIUM)
        try:
            texto = "❌ *Seu plano Premium foi cancelado ou expirou.*\n\nVocê pode renovar a qualquer momento em /planos."
            asyncio.run(app.bot.send_message(chat_id=telegram_id, text=texto, parse_mode="Markdown"))
        except Exception as e:
            print(f"[webhook_asaas] erro ao notificar cancelamento {telegram_id}: {e}")
        try:
            texto_admin = f"⚠️ Premium cancelado/expirado: ID {telegram_id} (status {status})"
            asyncio.run(app.bot.send_message(chat_id=ADMIN_ID, text=texto_admin))
        except Exception as e:
            print(f"[webhook_asaas] erro ao notificar admin cancelamento: {e}")
    return "OK", 200

@flask_app.route("/webhook_telegram", methods=["POST"])
def webhook_telegram():
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
            BotCommand("meuid", "Ver seu ID do Telegram"),
            BotCommand("premiumlist", "Listar usuários premium (admin)"),
            BotCommand("addpremium", "Adicionar premium manualmente (admin)"),
            BotCommand("delpremium", "Remover premium manualmente (admin)")
        ])
        asyncio.create_task(verificar_vencimentos(app))

    global app
    app = ApplicationBuilder().token(TOKEN).post_init(comandos_post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("planos", planos))
    app.add_handler(CommandHandler("duvida", duvida))
    app.add_handler(CommandHandler("meuid", meuid))
    app.add_handler(CommandHandler("premiumlist", premiumlist))
    app.add_handler(CommandHandler("addpremium", addpremium))
    app.add_handler(CommandHandler("delpremium", delpremium))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

    print("🤖 Bot ativo e monitorando planos premium...")
    app.run_polling()

if __name__ == "__main__":
    main()
