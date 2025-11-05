# bot.py
# Jet_TikTokShop Bot v4.6 - Unificado e corrigido para Render
# - Polling Telegram (sem webhook)
# - Flask para /health e webhook_asaas
# - Cookies suportam ENV base64 (COOKIES_IG_B64, COOKIES_SHOPEE_B64) ou variáveis cruas
# - Shopee fallback + Instagram cookies for private content

import os
import base64
import json
import re
import traceback
import logging
import asyncio
import aiohttp
import yt_dlp
from datetime import datetime, date, timedelta
from pathlib import Path
from flask import Flask, request
import threading

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# -----------------------
# logging
# -----------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jetbot")

# -----------------------
# Configurações
# -----------------------
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "5593153639"))
LIMITE_DIARIO = int(os.environ.get("LIMITE_DIARIO", "10"))

ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"

ARQUIVO_CONTADOR = "downloads.json"
ARQUIVO_PREMIUM = "premium.json"

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

# -----------------------
# Helpers para JSON
# -----------------------
def carregar_json(caminho):
    if os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def salvar_json(caminho, dados):
    with open(caminho, "w", encoding="utf-8") as f:
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
    logger.info(f"[premium] {user_id} -> validade {validade.isoformat()}")

# -----------------------
# Vencimentos
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
                logger.exception(f"[verificar_vencimentos] erro notificando {user_id}: {e}")
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
# Cookies: suporte a base64 e cru
# -----------------------
def salvar_cookie_b64(env_name, out_filename):
    val = os.environ.get(env_name)
    if not val:
        return None
    try:
        decoded = base64.b64decode(val)
    except Exception as e:
        logger.error(f"[cookie] {env_name} inválido base64: {e}")
        # tenta interpretar como raw (não base64)
        try:
            # se contiver \n representados
            raw = val.replace("\\n", "\n")
            p = SCRIPT_DIR / out_filename
            p.write_text(raw, encoding="utf-8")
            logger.info(f"[cookie] {env_name} salvo (texto cru) -> {out_filename}")
            return p
        except Exception as e2:
            logger.exception(f"[cookie] falha ao salvar {env_name}: {e2}")
            return None
    # se decodificou, tenta decod utf-8 e salvar
    try:
        text = decoded.decode("utf-8")
        p = SCRIPT_DIR / out_filename
        p.write_text(text, encoding="utf-8")
        logger.info(f"[cookie] {env_name} salvo (base64) -> {out_filename}")
        return p
    except UnicodeDecodeError:
        # pode ser binary cookie file (cookies.sqlite) — salve binário
        try:
            p = SCRIPT_DIR / out_filename
            with open(p, "wb") as f:
                f.write(decoded)
            logger.info(f"[cookie] {env_name} salvo (base64 binário) -> {out_filename}")
            return p
        except Exception as e:
            logger.exception(f"[cookie] falha ao escrever {env_name} binário: {e}")
            return None

# suporta: COOKIES_IG_B64, COOKIES_SHOPEE_B64, COOKIES_TIKTOK (raw), COOKIES_TIKTOK_B64 optional
COOKIES_INSTAGRAM = None
if "COOKIES_IG_B64" in os.environ:
    COOKIES_INSTAGRAM = salvar_cookie_b64("COOKIES_IG_B64", "cookies_instagram.txt")
elif "COOKIES_INSTAGRAM" in os.environ:
    # variável crua com \n's escaped
    try:
        raw = os.environ["COOKIES_INSTAGRAM"].replace("\\n", "\n")
        p = SCRIPT_DIR / "cookies_instagram.txt"
        p.write_text(raw, encoding="utf-8")
        COOKIES_INSTAGRAM = p
        logger.info("Cookie INSTAGRAM salvo (raw).")
    except Exception as e:
        logger.exception("Falha ao salvar COOKIES_INSTAGRAM raw: %s", e)

COOKIES_SHOPEE = None
if "COOKIES_SHOPEE_B64" in os.environ:
    COOKIES_SHOPEE = salvar_cookie_b64("COOKIES_SHOPEE_B64", "cookies_shopee.txt")
elif "COOKIES_SHOPEE" in os.environ:
    try:
        raw = os.environ["COOKIES_SHOPEE"].replace("\\n", "\n")
        p = SCRIPT_DIR / "cookies_shopee.txt"
        p.write_text(raw, encoding="utf-8")
        COOKIES_SHOPEE = p
        logger.info("Cookie SHOPEE salvo (raw).")
    except Exception as e:
        logger.exception("Falha ao salvar COOKIES_SHOPEE raw: %s", e)

COOKIES_TIKTOK = None
if "COOKIES_TIKTOK_B64" in os.environ:
    COOKIES_TIKTOK = salvar_cookie_b64("COOKIES_TIKTOK_B64", "cookies_tiktok.txt")
elif "COOKIES_TIKTOK" in os.environ:
    try:
        raw = os.environ["COOKIES_TIKTOK"].replace("\\n", "\n")
        p = SCRIPT_DIR / "cookies_tiktok.txt"
        p.write_text(raw, encoding="utf-8")
        COOKIES_TIKTOK = p
        logger.info("Cookie TIKTOK salvo (raw).")
    except Exception as e:
        logger.exception("Falha ao salvar COOKIES_TIKTOK raw: %s", e)

COOKIES_YOUTUBE = None
if "COOKIES_YOUTUBE_B64" in os.environ:
    COOKIES_YOUTUBE = salvar_cookie_b64("COOKIES_YOUTUBE_B64", "cookies_youtube.txt")
elif "COOKIES_YOUTUBE" in os.environ:
    try:
        raw = os.environ["COOKIES_YOUTUBE"].replace("\\n", "\n")
        p = SCRIPT_DIR / "cookies_youtube.txt"
        p.write_text(raw, encoding="utf-8")
        COOKIES_YOUTUBE = p
        logger.info("Cookie YOUTUBE salvo (raw).")
    except Exception as e:
        logger.exception("Falha ao salvar COOKIES_YOUTUBE raw: %s", e)

# -----------------------
# Flask app (health + asaas)
# -----------------------
flask_app = Flask(__name__)

@flask_app.route("/health", methods=["GET"])
def health():
    return "OK", 200

@flask_app.route("/webhook_asaas", methods=["POST"])
def webhook_asaas():
    try:
        data = request.json or {}
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
                # envio direto (sincrono dentro flask) - usa run_coroutine_threadsafe para evitar novos loops
                asyncio.get_event_loop().create_task(telegram_app.bot.send_message(chat_id=telegram_id, text=texto, parse_mode="Markdown"))
            except Exception as e:
                logger.exception(f"[webhook_asaas] erro ao notificar usuario {telegram_id}: {e}")
            try:
                texto_admin = (
                    f"📢 Novo Premium confirmado:\nID: {telegram_id}\nPlano: {descricao or 'não informado'}\n"
                    f"Validade: {USUARIOS_PREMIUM.get(str(telegram_id), {}).get('validade')}"
                )
                asyncio.get_event_loop().create_task(telegram_app.bot.send_message(chat_id=ADMIN_ID, text=texto_admin))
            except Exception as e:
                logger.exception(f"[webhook_asaas] erro ao notificar admin: {e}")
        elif status in ["CANCELED", "EXPIRED"]:
            USUARIOS_PREMIUM.pop(str(telegram_id), None)
            salvar_premium(USUARIOS_PREMIUM)
            try:
                texto = "❌ *Seu plano Premium foi cancelado ou expirou.*\n\nVocê pode renovar a qualquer momento em /planos."
                asyncio.get_event_loop().create_task(telegram_app.bot.send_message(chat_id=telegram_id, text=texto, parse_mode="Markdown"))
            except Exception as e:
                logger.exception(f"[webhook_asaas] erro ao notificar cancelamento {telegram_id}: {e}")
            try:
                texto_admin = f"⚠️ Premium cancelado/expirado: ID {telegram_id} (status {status})"
                asyncio.get_event_loop().create_task(telegram_app.bot.send_message(chat_id=ADMIN_ID, text=texto_admin))
            except Exception as e:
                logger.exception(f"[webhook_asaas] erro ao notificar admin cancelamento: {e}")

        return "OK", 200
    except Exception as e:
        logger.exception("Erro em webhook_asaas: %s", e)
        return "ERROR", 500

# -----------------------
# Funções utilitárias de download
# -----------------------
async def baixar_shopee_por_html(url, destino: Path):
    """Tenta extrair video_url do HTML (fallback). Retorna caminho do arquivo ou None."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as r:
                html = await r.text()
        m = re.search(r'"video_url":"(https:\\/\\/sv\.shopee\.com\.br\\/.*?\.mp4)"', html)
        if not m:
            # tenta encontrar outro padrão share-video
            m2 = re.search(r'(https:\\/\\/sv\.shopee\.com\\.br\\/share-video\\/.*?\\.mp4)', html)
            if m2:
                video_url = m2.group(1).replace("\\/", "/")
            else:
                return None
        else:
            video_url = m.group(1).replace("\\/", "/")

        fname = destino / f"shopee_{int(datetime.now().timestamp())}.mp4"
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url) as resp:
                if resp.status != 200:
                    logger.error("Shopee fallback status %s for %s", resp.status, video_url)
                    return None
                data = await resp.read()
                with open(fname, "wb") as f:
                    f.write(data)
        return fname
    except Exception:
        logger.exception("Erro no fallback Shopee")
        return None

def buscar_arquivo_fallback(info):
    """Procura arquivo real no diretório downloads quando prepare_filename deu problema."""
    id_ = info.get("id")
    if not id_:
        return None
    candidates = list(DOWNLOADS_DIR.glob(f"{id_}*"))
    if candidates:
        return candidates[0]
    return None

# -----------------------
# Comandos do bot (Telegram)
# -----------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensagem = (
        "🎬 *Bem-vindo(a) ao bot Jet_TikTokShop!*\n\n"
        "👉 Envie o link do vídeo que deseja baixar.\n"
        f"⚠️ Usuário Free: até *{LIMITE_DIARIO} vídeos/dia*\n"
        "💎 Premium: downloads ilimitados.\n\n"
        "✨ Use o menu (📎 ➜ /) para ver os comandos."
    )
    await update.message.reply_text(mensagem, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

async def planos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    planos_disponiveis = [
        {"descricao": "1 Mês", "valor": 9.90, "url": "https://www.asaas.com/c/knu5vub6ejc2yyja"},
        {"descricao": "3 Meses", "valor": 25.90, "url": "https://www.asaas.com/c/o9pg4uxrpgwnmqzd"},
        {"descricao": "1 Ano", "valor": 89.90, "url": "https://www.asaas.com/c/puto9coszhwgprqc"}
    ]
    keyboard = [[InlineKeyboardButton(f"💎 {p['descricao']} - R$ {p['valor']}", url=p['url'])] for p in planos_disponiveis]
    await update.message.reply_text("💎 Escolha seu plano Premium:", reply_markup=InlineKeyboardMarkup(keyboard))

async def duvida_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Contato: lavimurtha@gmail.com", parse_mode="Markdown")

async def meuid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Seu Telegram ID é: `{update.message.from_user.id}`", parse_mode="Markdown")

# função de baixar geral (integração yt-dlp + fallback Shopee)
async def baixar_video_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (update.message.text or "").strip()
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
        # resolve redirects (pin.it etc)
        if "pin.it/" in texto:
            async with aiohttp.ClientSession() as s:
                async with s.get(texto, allow_redirects=True) as r:
                    texto = str(r.url)

        # special-case Shopee: if it looks like a shopee universal link that yt-dlp won't handle,
        # try fallback extraction first
        if ("shopee.com.br" in texto or "sv.shopee.com.br" in texto):
            # attempt fallback extraction (safer)
            destino = DOWNLOADS_DIR
            fallback_file = await baixar_shopee_por_html(texto, destino)
            if fallback_file:
                # send file
                with open(fallback_file, "rb") as f:
                    await update.message.reply_video(f, caption="✅ Aqui está seu vídeo da Shopee!")
                os_remove_safe(fallback_file)
                if not is_premium(user_id):
                    incrementar_download(user_id)
                return
            # else continue to try with yt-dlp

        out_template = str(DOWNLOADS_DIR / f"%(id)s-%(title)s.%(ext)s")
        ydl_opts = {"outtmpl": out_template, "format": "best", "quiet": True, "noplaylist": True, "merge_output_format": "mp4"}

        # attach cookiefile when available
        if "instagram.com" in texto and COOKIES_INSTAGRAM and COOKIES_INSTAGRAM.exists():
            ydl_opts["cookiefile"] = str(COOKIES_INSTAGRAM)
        elif "tiktok.com" in texto and COOKIES_TIKTOK and COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)
        elif "shopee" in texto and COOKIES_SHOPEE and COOKIES_SHOPEE.exists():
            ydl_opts["cookiefile"] = str(COOKIES_SHOPEE)
            ydl_opts["headers"] = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/117.0.0.0 Safari/537.36"
                ),
                "Referer": "https://shopee.com.br/",
            }
        elif "youtube.com" in texto and COOKIES_YOUTUBE and COOKIES_YOUTUBE.exists():
            ydl_opts["cookiefile"] = str(COOKIES_YOUTUBE)

        # run yt-dlp in executor (blocking)
        def run_ydl(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info, ydl

        loop = asyncio.get_running_loop()
        info, ydl_obj = await loop.run_in_executor(None, lambda: run_ydl(texto))

        # try prepare filename, if missing fallback to search
        try:
            file_path = ydl_obj.prepare_filename(info)
        except Exception:
            file_path = None

        # if file_path absent or not exists, try fallback search
        if not file_path or not Path(file_path).exists():
            fb = buscar_arquivo_fallback(info)
            if fb:
                file_path = str(fb)

        if not file_path or not Path(file_path).exists():
            raise FileNotFoundError(f"Arquivo não encontrado após o download (id={info.get('id')})")

        # send as video, fallback to document
        try:
            with open(file_path, "rb") as f:
                await update.message.reply_video(f, caption="✅ Aqui está seu vídeo!")
        except Exception:
            with open(file_path, "rb") as f:
                await update.message.reply_document(f, caption="✅ Aqui está seu arquivo!")

        # cleanup
        os_remove_safe(file_path)
        if not is_premium(user_id):
            incrementar_download(user_id)

    except Exception as e:
        logger.exception("Erro ao baixar:")
        await update.message.reply_text(f"❌ Erro ao baixar: {e}")

# -----------------------
# Admin commands
# -----------------------
async def premiumlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    texto = "\n".join([f"• {uid} (até {info.get('validade')})" for uid, info in USUARIOS_PREMIUM.items()])
    await update.message.reply_text("💎 Usuários Premium:\n" + texto)

async def addpremium_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def delpremium_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
# Utils
# -----------------------
def os_remove_safe(path):
    try:
        if isinstance(path, (str, Path)):
            p = Path(path)
            if p.exists():
                p.unlink()
    except Exception:
        logger.exception("Erro ao remover arquivo %s", path)

# -----------------------
# Flask route to optionally receive Telegram webhook (not used) - keep for compatibility
# -----------------------
@flask_app.route("/webhook_telegram", methods=["POST"])
def webhook_telegram():
    # keep simple: not used for updates (we use polling), but accept to avoid 404 if Telegram sends
    return "OK", 200

# -----------------------
# Inicialização e main
# -----------------------
def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)

# build telegram app (polling)
telegram_app = ApplicationBuilder().token(TOKEN).build()

def main():
    # register commands & handlers
    telegram_app.add_handler(CommandHandler("start", start_cmd))
    telegram_app.add_handler(CommandHandler("planos", planos_cmd))
    telegram_app.add_handler(CommandHandler("duvida", duvida_cmd))
    telegram_app.add_handler(CommandHandler("meuid", meuid_cmd))
    telegram_app.add_handler(CommandHandler("premiumlist", premiumlist_cmd))
    telegram_app.add_handler(CommandHandler("addpremium", addpremium_cmd))
    telegram_app.add_handler(CommandHandler("delpremium", delpremium_cmd))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video_cmd))

    # post init: set bot commands and start vencimentos checker
    async def post_init(app):
        try:
            await app.bot.set_my_commands([
                BotCommand("start", "Iniciar o bot"),
                BotCommand("planos", "Ver planos Premium"),
                BotCommand("duvida", "Ajuda e contato"),
                BotCommand("meuid", "Ver seu ID do Telegram"),
                BotCommand("premiumlist", "Listar usuários premium (admin)"),
                BotCommand("addpremium", "Adicionar premium manualmente (admin)"),
                BotCommand("delpremium", "Remover premium manualmente (admin)")
            ])
        except Exception:
            logger.exception("Falha ao setar comandos")
        # start vencimentos loop
        asyncio.create_task(verificar_vencimentos(app))

    # start Flask in thread
    threading.Thread(target=run_flask, daemon=True).start()

    # run telegram polling (blocking)
    try:
        telegram_app.post_init = post_init
        logger.info("🤖 Bot ativo e monitorando planos premium...")
        telegram_app.run_polling()
    except Exception:
        logger.exception("Erro no polling")

if __name__ == "__main__":
    main()
