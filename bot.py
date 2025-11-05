# Jet_TikTokShop Bot v4.6 - Adicionado suporte a cookies Base64 (Instagram + Shopee)
# Totalmente compatível com Render e sistema Premium

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp, os, json, aiohttp, base64
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

# -----------------------
# Cookies TikTok / Instagram / Shopee
# -----------------------

# TikTok cookies (texto direto)
COOKIES_TIKTOK = SCRIPT_DIR / "cookies_tiktok.txt"
if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    with open(COOKIES_TIKTOK, "w", encoding="utf-8") as f:
        f.write(os.environ["COOKIES_TIKTOK"])

# Instagram cookies (base64)
COOKIES_IG = SCRIPT_DIR / "cookies_instagram.txt"
if "COOKIES_IG_B64" in os.environ:
    try:
        decoded = base64.b64decode(os.environ["COOKIES_IG_B64"]).decode("utf-8")
        with open(COOKIES_IG, "w", encoding="utf-8") as f:
            f.write(decoded)
        print("✅ Cookies do Instagram carregados com sucesso.")
    except Exception as e:
        print(f"⚠️ Erro ao decodificar COOKIES_IG_B64: {e}")

# Shopee cookies (base64)
COOKIES_SHOPEE = SCRIPT_DIR / "cookies_shopee.txt"
if "COOKIES_SHOPEE_B64" in os.environ:
    try:
        decoded = base64.b64decode(os.environ["COOKIES_SHOPEE_B64"]).decode("utf-8")
        with open(COOKIES_SHOPEE, "w", encoding="utf-8") as f:
            f.write(decoded)
        print("✅ Cookies da Shopee carregados com sucesso.")
    except Exception as e:
        print(f"⚠️ Erro ao decodificar COOKIES_SHOPEE_B64: {e}")

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
# Premium (estrutura: dict { "<telegram_id>": {"validade": "YYYY-MM-DD"} })
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
                    await app.bot.send_message(chat_id=int(user_id), text="⚠️ *Seu plano Premium vence amanhã!*", parse_mode="Markdown")
                elif dias_restantes == 0:
                    await app.bot.send_message(chat_id=int(user_id), text="💔 *Seu plano Premium vence hoje!*", parse_mode="Markdown")
                elif dias_restantes < 0:
                    await app.bot.send_message(chat_id=int(user_id), text="❌ Seu plano Premium expirou.")
                    USUARIOS_PREMIUM.pop(user_id, None)
                    salvar_premium(USUARIOS_PREMIUM)
            except Exception:
                pass
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
    msg = (
        "🎬 *Bem-vindo(a) ao bot Jet_TikTokShop!*\n\n"
        "👉 Envie o link do vídeo que deseja baixar.\n"
        "⚠️ Usuário Free: até *10 vídeos/dia*\n"
        "💎 Premium: downloads ilimitados.\n\n"
        "✨ Use o menu (📎 ➜ /) para ver os comandos."
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

async def planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    planos_disponiveis = [
        {"descricao": "1 Mês", "valor": 9.90, "url": "https://www.asaas.com/c/knu5vub6ejc2yyja"},
        {"descricao": "3 Meses", "valor": 25.90, "url": "https://www.asaas.com/c/o9pg4uxrpgwnmqzd"},
        {"descricao": "1 Ano", "valor": 89.90, "url": "https://www.asaas.com/c/puto9coszhwgprqc"}
    ]
    keyboard = [[InlineKeyboardButton(f"💎 {p['descricao']} - R$ {p['valor']}", url=p['url'])] for p in planos_disponiveis]
    await update.message.reply_text("💎 Escolha seu plano Premium:", reply_markup=InlineKeyboardMarkup(keyboard))

async def duvida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Contato: lavimurtha@gmail.com")

async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Seu Telegram ID é: `{update.message.from_user.id}`", parse_mode="Markdown")

import base64

import base64
import os
import yt_dlp
import aiohttp
import asyncio
import traceback

# -----------------------
# Download de vídeo (corrigido e compatível com Stories do Instagram)
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

        safe_id = "".join(c for c in texto if c.isalnum())[-12:]
        out_template = str(DOWNLOADS_DIR / f"{safe_id}.%(ext)s")

        ydl_opts = {
            "outtmpl": out_template,
            "format": "bestvideo+bestaudio/best",
            "quiet": True,
            "merge_output_format": "mp4",
            "retries": 3,
            "noprogress": True,
        }

        def salvar_cookie_env(nome_variavel, arquivo_destino):
            conteudo = os.environ.get(nome_variavel)
            if not conteudo:
                return None
            try:
                decoded = base64.b64decode(conteudo).decode("utf-8")
                conteudo = decoded
            except Exception:
                pass  # já é texto plano
            conteudo = conteudo.replace("\\n", "\n").replace("\r\n", "\n")
            if not conteudo.startswith("# Netscape"):
                conteudo = "# Netscape HTTP Cookie File\n" + conteudo
            with open(arquivo_destino, "w", encoding="utf-8") as f:
                f.write(conteudo)
            return arquivo_destino

        if "instagram.com" in texto:
            cookie_path = salvar_cookie_env("COOKIES_IG_B64", "cookies_instagram.txt")
            if cookie_path:
                ydl_opts["cookiefile"] = cookie_path
                print("[COOKIES] Usando cookies do Instagram.")
        elif "shopee.com" in texto:
            cookie_path = salvar_cookie_env("COOKIES_SHOPEE_B64", "cookies_shopee.txt")
            if cookie_path:
                ydl_opts["cookiefile"] = cookie_path
                print("[COOKIES] Usando cookies da Shopee.")
        elif "tiktok.com" in texto and COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)
            print("[COOKIES] Usando cookies do TikTok.")

        def run_ydl(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info, ydl

        loop = asyncio.get_running_loop()
        info, ydl_obj = await loop.run_in_executor(None, lambda: run_ydl(texto))
        file_path = ydl_obj.prepare_filename(info)

        # 🔧 Corrige arquivos sem extensão
        if not os.path.splitext(file_path)[1] or file_path.endswith(".NA"):
            possible_mp4 = file_path.replace(".NA", ".mp4")
            if os.path.exists(possible_mp4):
                file_path = possible_mp4
            else:
                # tenta achar arquivo com mesmo prefixo
                prefix = os.path.splitext(file_path)[0]
                for f in os.listdir(DOWNLOADS_DIR):
                    if f.startswith(os.path.basename(prefix)):
                        file_path = str(DOWNLOADS_DIR / f)
                        break

        file_path = os.path.join("downloads", file_name)
if os.path.exists(file_path):
    with open(file_path, "rb") as f:
        await update.message.reply_video(f, caption="✅ Aqui está seu vídeo!")
    os.remove(file_path)
else:
    await update.message.reply_text("Erro ao baixar: Arquivo não encontrado após o download.")


# -----------------------
# Flask Webhook
# -----------------------
flask_app = Flask(__name__)

@flask_app.route("/health", methods=["GET"])
def health():
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
        asyncio.create_task(verificar_vencimentos(app))

    global app
    app = ApplicationBuilder().token(TOKEN).post_init(comandos_post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("planos", planos))
    app.add_handler(CommandHandler("duvida", duvida))
    app.add_handler(CommandHandler("meuid", meuid))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

    print("🤖 Bot ativo e pronto para Webhook...")
    app.run_polling()

if __name__ == "__main__":
    main()





