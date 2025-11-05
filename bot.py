import os
import base64
import logging
import asyncio
import aiohttp
import yt_dlp
import tempfile
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pathlib import Path
import nest_asyncio
import traceback

nest_asyncio.apply()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================================
# VARIÁVEIS DE AMBIENTE
# ==========================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
PORT = int(os.getenv("PORT", 5000))

# ==========================================================
# FUNÇÃO PARA SALVAR COOKIES A PARTIR DO BASE64
# ==========================================================
SCRIPT_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

def salvar_cookie(nome_env, nome_arquivo):
    valor_b64 = os.getenv(nome_env)
    if valor_b64:
        try:
            conteudo = base64.b64decode(valor_b64).decode("utf-8")
            caminho = SCRIPT_DIR / nome_arquivo
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(conteudo)
            logger.info(f"[OK] Cookie salvo: {nome_arquivo}")
            return caminho
        except Exception as e:
            logger.error(f"[ERRO] Falha ao salvar cookie {nome_env}: {e}")
    return None

# Cookies decodificados do Render
COOKIES_INSTAGRAM = salvar_cookie("COOKIES_IG_B64", "cookies_instagram.txt")
COOKIES_TIKTOK = salvar_cookie("COOKIES_TIKTOK", "cookies_tiktok.txt")
COOKIES_SHOPEE = salvar_cookie("COOKIES_SHOPEE_B64", "cookies_shopee.txt")
COOKIES_YOUTUBE = salvar_cookie("COOKIES_YOUTUBE", "cookies_youtube.txt")

# ==========================================================
# FLASK APP (para webhook)
# ==========================================================
app = Flask(__name__)

# ==========================================================
# COMANDOS DO BOT
# ==========================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Olá! Envie um link do Instagram, Shopee, TikTok ou YouTube para baixar o vídeo."
    )

# ==========================================================
# FUNÇÃO PRINCIPAL DE DOWNLOAD
# ==========================================================
async def baixar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    user_id = update.message.from_user.id

    if not texto.startswith("http"):
        await update.message.reply_text("❌ Envie um link válido.")
        return

    await update.message.reply_text("⏳ Baixando... aguarde alguns segundos...")

    try:
        # Corrige links de redirecionamento
        if "pin.it/" in texto:
            async with aiohttp.ClientSession() as s:
                async with s.get(texto, allow_redirects=True) as r:
                    texto = str(r.url)

        out_template = str(DOWNLOADS_DIR / f"%(id)s-%(title)s.%(ext)s")
        ydl_opts = {
            "outtmpl": out_template,
            "quiet": True,
            "format": "best[height<=720]",
            "merge_output_format": "mp4",
        }

        # --- Usa cookies conforme o domínio ---
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

        # --- Execução do download ---
        def run_ydl(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info, ydl

        loop = asyncio.get_running_loop()
        info, ydl_obj = await loop.run_in_executor(None, lambda: run_ydl(texto))
        file_path = ydl_obj.prepare_filename(info)

        # --- Envia o vídeo ---
        try:
            with open(file_path, "rb") as f:
                await update.message.reply_video(
                    video=f,
                    caption="✅ Aqui está seu vídeo!",
                    timeout=180
                )
        except Exception:
            with open(file_path, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    caption="⚙️ Envio alternativo (arquivo grande)",
                    timeout=180
                )

        os.remove(file_path)

    except Exception as e:
        traceback.print_exc()
        await update.message.reply_text(f"❌ Erro ao baixar: {e}")

# ==========================================================
# HANDLERS DO TELEGRAM
# ==========================================================
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

# ==========================================================
# FLASK WEBHOOK
# ==========================================================
@app.route(f"/webhook", methods=["POST"])
async def webhook():
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, application.bot)
        await application.initialize()
        await application.process_update(update)
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        return jsonify({"ok": False, "erro": str(e)}), 500

@app.route("/")
def home():
    return jsonify({"ok": True, "status": "Bot de vídeo ativo!"})

# ==========================================================
# MAIN
# ==========================================================
if __name__ == "__main__":
    logger.info("🚀 Iniciando bot Flask + Telegram...")
    app.run(host="0.0.0.0", port=PORT)
