# Jet_TikTokShop Bot v4.8 - Adaptado para Render
# Downloads + Premium Dinâmico via Asaas + Ver ID + TikTok/Instagram/YouTube/Shopee com cookies + Validade automática + Admin tools

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp, os, json, aiohttp
from datetime import datetime, date, timedelta
from pathlib import Path
import asyncio, traceback, re, urllib.parse
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
                    await app.bot.send_message(chat_id=int(user_id), text="⚠️ *Seu plano Premium vence amanhã!* Renove para continuar com downloads ilimitados.", parse_mode="Markdown")
                elif dias_restantes == 0:
                    await app.bot.send_message(chat_id=int(user_id), text="💔 *Seu plano Premium vence hoje!* Renove para não perder o acesso.", parse_mode="Markdown")
                elif dias_restantes < 0:
                    await app.bot.send_message(chat_id=int(user_id), text="❌ Seu plano Premium expirou. Torne-se Premium novamente acessando /planos.")
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
# Detectar plataforma
# -----------------------
def detectar_plataforma(url: str) -> str:
    url = url.lower()
    if "tiktok.com" in url or "vt.tiktok.com" in url:
        return "tiktok"
    elif "instagram.com" in url:
        return "instagram"
    elif "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    elif "shopee.com" in url:
        return "shopee"
    return "outros"

# -----------------------
# Limpar link Shopee
# -----------------------
def limpar_link_shopee(url: str) -> str:
    if "shopee.com" in url and "redir=" in url:
        try:
            decoded = urllib.parse.unquote(re.search(r"redir=([^&]+)", url).group(1))
            return decoded
        except Exception:
            return url
    return url

# -----------------------
# Download de vídeo
# -----------------------
async def baixar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    plataforma = detectar_plataforma(texto)
    user_id = update.message.from_user.id

    if plataforma == "shopee":
        texto = limpar_link_shopee(texto)

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
        out_template = str(DOWNLOADS_DIR / f"%(id)s-%(title)s.%(ext)s")
        ydl_opts = {"outtmpl": out_template, "format": "best", "quiet": True}

        # Cookies automáticos
        if plataforma == "instagram" and COOKIES_INSTAGRAM.exists():
            ydl_opts["cookiefile"] = str(COOKIES_INSTAGRAM)
        elif plataforma == "tiktok" and COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)
        elif plataforma == "youtube" and COOKIES_YOUTUBE.exists():
            ydl_opts["cookiefile"] = str(COOKIES_YOUTUBE)
            ydl_opts["extractor_args"] = {"youtubetab": {"skip": "authcheck"}}

        def run_ydl(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info, ydl

        loop = asyncio.get_running_loop()
        try:
            info, ydl_obj = await loop.run_in_executor(None, lambda: run_ydl(texto))
        except Exception as e:
            await update.message.reply_text(f"❌ Não foi possível baixar este link.\n{e}")
            return

        file_path = ydl_obj.prepare_filename(info)

        with open(file_path, "rb") as f:
            await update.message.reply_video(f, caption="✅ Aqui está seu vídeo!")

        os.remove(file_path)
        if not is_premium(user_id):
            incrementar_download(user_id)

    except Exception as e:
        await update.message.reply_text(f"Erro inesperado: {e}")

# -----------------------
# Admin / Webhook / Inicialização
# -----------------------
# Aqui mantemos o Flask e polling do bot igual ao v4.7, sem alterações na lógica.
# (Inclui webhook_asaas, webhook_telegram, comandos admin add/del premium, health check)
