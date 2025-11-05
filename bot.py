import os
import base64
import logging
import asyncio
import aiofiles
import yt_dlp
import tempfile
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pathlib import Path
import nest_asyncio

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
# FUNÇÕES DO BOT
# ==========================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Olá! Envie um link do Instagram, Shopee, TikTok ou YouTube para baixar o vídeo.")

async def baixar_video(url: str) -> str:
    """Baixa vídeo com yt-dlp e retorna o caminho local do arquivo."""
    try:
        logger.info(f"Baixando vídeo: {url}")
        temp_dir = Path(tempfile.gettempdir())
        output_path = temp_dir / "%(id)s.%(ext)s"

        ydl_opts = {
            "outtmpl": str(output_path),
            "quiet": True,
            "noplaylist": True,
            "merge_output_format": "mp4",
            "retries": 5,
            "skip_unavailable_fragments": True,
        }

        # Seleciona cookies de acordo com o domínio
        if "instagram.com" in url and COOKIES_INSTAGRAM:
            ydl_opts["cookiefile"] = str(COOKIES_INSTAGRAM)
        elif "tiktok.com" in url and COOKIES_TIKTOK:
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)
        elif "shopee" in url and COOKIES_SHOPEE:
            ydl_opts["cookiefile"] = str(COOKIES_SHOPEE)
            ydl_opts["headers"] = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/117.0.0.0 Safari/537.36"
                ),
                "Referer": "https://shopee.com.br/",
            }
            ydl_opts["format"] = "mp4/best"
        elif "youtube.com" in url and COOKIES_YOUTUBE:
            ydl_opts["cookiefile"] = str(COOKIES_YOUTUBE)

        # Executa o download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if os.path.exists(filename):
                return filename
            raise FileNotFoundError(f"Arquivo não encontrado após o download: {filename}")

    except Exception as e:
        logger.error(f"Erro ao baixar vídeo: {e}")
        return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagens de texto com links."""
    if not update.message or not update.message.text:
        return

    url = update.message.text.strip()
    chat_id = update.effective_chat.id
    await update.message.reply_text("🔄 Baixando o vídeo, aguarde...")

    file_path = await baixar_video(url)
    if not file_path:
        await context.bot.send_message(chat_id, "❌ Erro ao baixar o vídeo. Verifique o link ou os cookies.")
        return

    try:
        async with aiofiles.open(file_path, "rb") as f:
            await context.bot.send_video(chat_id=chat_id, video=await f.read())
        os.remove(file_path)
    except Exception as e:
        logger.error(f"Erro ao enviar vídeo: {e}")
        await context.bot.send_message(chat_id, "⚠️ Erro ao enviar o vídeo. Tente novamente.")

# ==========================================================
# TELEGRAM HANDLERS
# ==========================================================
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# ==========================================================
# FLASK WEBHOOK ROUTE
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
# MAIN (Render)
# ==========================================================
if __name__ == "__main__":
    logger.info("🚀 Iniciando bot Flask + Telegram...")
    app.run(host="0.0.0.0", port=PORT)
