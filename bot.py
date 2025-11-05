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

    await update.message.reply_text("⏳ Baixando... aguarde alguns segundos...")

    try:
        # Caso o link seja um redirecionamento (como pin.it)
        if "pin.it/" in texto:
            async with aiohttp.ClientSession() as s:
                async with s.get(texto, allow_redirects=True) as r:
                    texto = str(r.url)

        out_template = str(DOWNLOADS_DIR / f"%(id)s-%(title)s.%(ext)s")
        ydl_opts = {
            "outtmpl": out_template,
            "quiet": True,
            "format": "best[height<=720]",  # limita a 720p (evita arquivos enormes)
        }

        # --- Usa cookies conforme o domínio ---
        if "instagram.com" in texto and COOKIES_INSTAGRAM.exists():
            ydl_opts["cookiefile"] = str(COOKIES_INSTAGRAM)
        elif "tiktok.com" in texto and COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)
        elif "shopee" in texto:
            # suporte para Shopee (cookies via variável base64)
            cookies_shopee_path = SCRIPT_DIR / "cookies_shopee.txt"
            if "COOKIES_SHOPEE_B64" in os.environ:
                import base64
                conteudo = base64.b64decode(os.environ["COOKIES_SHOPEE_B64"]).decode("utf-8")
                with open(cookies_shopee_path, "w", encoding="utf-8") as f:
                    f.write(conteudo)
                ydl_opts["cookiefile"] = str(cookies_shopee_path)

        # --- Execução do download ---
        def run_ydl(url):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info, ydl

        loop = asyncio.get_running_loop()
        info, ydl_obj = await loop.run_in_executor(None, lambda: run_ydl(texto))
        file_path = ydl_obj.prepare_filename(info)

        # --- Envio com timeout estendido e fallback ---
        try:
            with open(file_path, "rb") as f:
                await update.message.reply_video(
                    video=f,
                    caption="✅ Aqui está seu vídeo!",
                    timeout=180  # até 3 minutos para upload
                )
        except Exception as e:
            # fallback: envia como documento se o Telegram não aceitar como vídeo
            with open(file_path, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    caption="⚙️ Envio alternativo (arquivo grande)",
                    timeout=180
                )

        os.remove(file_path)
        if not is_premium(user_id):
            incrementar_download(user_id)

    except Exception as e:
        traceback.print_exc()
        await update.message.reply_text(f"❌ Erro ao baixar: {e}")

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

