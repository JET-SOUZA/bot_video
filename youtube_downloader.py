# youtube_downloader.py
import yt_dlp
import os
from telegram import Update
from telegram.ext import ContextTypes

DOWNLOAD_DIR = "downloads/yt"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

async def download_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Baixa vídeo do YouTube e envia pelo Telegram"""
    await update.message.reply_text("Processando vídeo do YouTube...")

    ydl_opts = {
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        'format': 'best',  # você pode alterar para 'bestvideo+bestaudio/best'
        'noplaylist': True,  # evita baixar playlists
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        # Envia o vídeo para o Telegram
        await context.bot.send_video(chat_id=update.effective_chat.id, video=open(filename, 'rb'))

        # Remove o arquivo depois de enviar
        os.remove(filename)
    except Exception as e:
        await update.message.reply_text(f"Erro ao baixar o vídeo do YouTube: {e}")
