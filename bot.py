# Jet TikTokShop Bot - Arquitetura C (Render + GitHub)
# PTB20 Webhook + Asaas + Shopee Universal Patch + yt-dlp
# Atualização 2025-11: addpremium/delpremium + menu admin + mobile fix (transcode fallback)

import os
import json
import requests
import asyncio
import traceback
from datetime import datetime, date
from pathlib import Path
from urllib.parse import unquote
import re
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp
import nest_asyncio

# ---------------------------------------------------------
# TOKEN (Render)
# ---------------------------------------------------------
TOKEN = (
    os.environ.get("TOKEN")
    or os.environ.get("BOT_TOKEN")
    or os.environ.get("TELEGRAM_TOKEN")
    or os.environ.get("TG_BOT_TOKEN")
)
if not TOKEN:
    raise ValueError("Nenhum token encontrado. Configure TOKEN ou BOT_TOKEN no Render.")

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY")
ASAAS_BASE_URL = "https://www.asaas.com/api/v3"
ADMIN_ID = 5593153639
LIMITE_DIARIO = 10
PORT = int(os.environ.get("PORT", 10000))

SCRIPT_DIR = Path(__file__).parent.resolve()
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

ARQUIVO_CONTADOR = SCRIPT_DIR / "downloads.json"
ARQUIVO_PREMIUM = SCRIPT_DIR / "premium.json"
COOKIES_TIKTOK = SCRIPT_DIR / "cookies.txt"

if "COOKIES_TIKTOK" in os.environ and not COOKIES_TIKTOK.exists():
    with open(COOKIES_TIKTOK, "w") as f:
        f.write(os.environ["COOKIES_TIKTOK"])

# ---------------------------------------------------------
# JSON UTILS
# ---------------------------------------------------------
def load_json(path):
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return {}


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


# ---------------------------------------------------------
# PREMIUM
# ---------------------------------------------------------
def load_premium():
    data = load_json(ARQUIVO_PREMIUM)
    return set(map(int, data.get("premium_users", [])))


def save_premium(users):
    save_json(ARQUIVO_PREMIUM, {"premium_users": list(users)})


USUARIOS_PREMIUM = load_premium()
USUARIOS_PREMIUM.add(ADMIN_ID)
save_premium(USUARIOS_PREMIUM)

# ---------------------------------------------------------
# ASAAS — PREMIUM AUTOMÁTICO
# ---------------------------------------------------------
def verificar_pagamentos_asaas():
    try:
        if not ASAAS_API_KEY:
            print("Asaas desativado (sem API KEY).")
            return
        url = f"{ASAAS_BASE_URL}/payments?status=CONFIRMED&limit=100"
        headers = {"access_token": ASAAS_API_KEY}
        data = requests.get(url, headers=headers, timeout=10).json()
        for p in data.get("data", []):
            if "metadata" in p and "telegram_id" in p["metadata"]:
                uid = int(p["metadata"]["telegram_id"])
                USUARIOS_PREMIUM.add(uid)
        save_premium(USUARIOS_PREMIUM)
    except Exception as e:
        print("Erro Asaas:", e)

# ---------------------------------------------------------
# LIMITE DIÁRIO
# ---------------------------------------------------------
def verificar_limite(uid):
    data = load_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())
    if str(uid) not in data or data[str(uid)]["data"] != hoje:
        data[str(uid)] = {"data": hoje, "downloads": 0}
        save_json(ARQUIVO_CONTADOR, data)
    return data[str(uid)]["downloads"]


def incrementar_download(uid):
    data = load_json(ARQUIVO_CONTADOR)
    hoje = str(date.today())
    if str(uid) not in data or data[str(uid)]["data"] != hoje:
        data[str(uid)] = {"data": hoje, "downloads": 1}
    else:
        data[str(uid)]["downloads"] += 1
    save_json(ARQUIVO_CONTADOR, data)
    return data[str(uid)]["downloads"]

# ---------------------------------------------------------
# COMANDOS
# ---------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    texto = (
        "🎬 *Jet TikTokShop Bot*\n\n"
        "Envie um link para baixar vídeo.\n"
        "⚠️ Free: 10/dia\n"
        "💎 Premium: ilimitado"
    )
    botoes = [
        [InlineKeyboardButton("💎 Planos", callback_data="planos")],
        [InlineKeyboardButton("🆘 Suporte", callback_data="duvida")],
    ]
    if user_id == ADMIN_ID:
        botoes += [
            [InlineKeyboardButton("➕ Add Premium", callback_data="addpremium")],
            [InlineKeyboardButton("➖ Remover Premium", callback_data="delpremium")],
        ]
    await update.message.reply_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("💎 1 Mês – R$ 9,90", url="https://www.asaas.com/c/knu5vub6ejc2yyja")],
        [InlineKeyboardButton("💎 3 Meses – R$ 25,90", url="https://www.asaas.com/c/o9pg4uxrpgwnmqzd")],
        [InlineKeyboardButton("💎 1 Ano – R$ 89,90", url="https://www.asaas.com/c/puto9coszhwgprqc")],
    ]
    await update.message.reply_text("💎 Planos Premium:", reply_markup=InlineKeyboardMarkup(kb))


async def duvida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Suporte: lavimurtha@gmail.com")


async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Seu ID: {update.message.from_user.id}")

# ---------------------------------------------------------
# ADMIN COMANDOS MANUAIS
# ---------------------------------------------------------
async def addpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Apenas o admin pode usar este comando.")
    if not context.args:
        return await update.message.reply_text("Uso: /addpremium <user_id>")
    uid = int(context.args[0])
    USUARIOS_PREMIUM.add(uid)
    save_premium(USUARIOS_PREMIUM)
    await update.message.reply_text(f"✅ Usuário {uid} adicionado ao Premium!")


async def delpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Apenas o admin pode usar este comando.")
    if not context.args:
        return await update.message.reply_text("Uso: /delpremium <user_id>")
    uid = int(context.args[0])
    if uid in USUARIOS_PREMIUM:
        USUARIOS_PREMIUM.remove(uid)
        save_premium(USUARIOS_PREMIUM)
        await update.message.reply_text(f"❌ Usuário {uid} removido do Premium.")
    else:
        await update.message.reply_text("Usuário não está no Premium.")

# ---------------------------------------------------------
# SHOPEE UNIVERSAL PATCH 2025
# ---------------------------------------------------------
def extrair_video_shopee(url):
    if "br.shp.ee" in url or "shp.ee" in url:
        try:
            r = requests.head(url, allow_redirects=True, timeout=10)
            url = r.url
        except:
            pass
    if "redir=" in url:
        try:
            redir = re.search(r"redir=([^&]+)", url).group(1)
            url = unquote(redir)
        except:
            pass

    m = re.search(r"/share-video/([A-Za-z0-9=_\-]+)", url)
    if not m:
        try:
            html = requests.get(url, timeout=10).text
            for regex in [
                r"/share-video/([A-Za-z0-9=_\-]+)",
            ]:
                mm = re.search(regex, html)
                if mm:
                    m = mm
                    break
        except:
            pass
    if not m:
        return None

    share_id = m.group(1)
    api_url = f"https://sv.shopee.com.br/api/v4/share/video?shareVideoId={share_id}"
    try:
        data = requests.get(api_url, timeout=10).json()
    except:
        data = {}

    video_url = (
        data.get("data", {}).get("play")
        or data.get("data", {}).get("video_url")
        or data.get("data", {}).get("url")
        or (data.get("data", {}).get("videos", [{}])[0].get("url") if data.get("data", {}).get("videos") else None)
        or data.get("data", {}).get("path")
    )
    if not video_url:
        try:
            html = requests.get(url, timeout=10).text
            for regex in [
                r"https?://[^\s\"']+\.mp4",
                r"https?://[^\s\"']+\.m3u8[^\s\"']*",
                r'"url":"(https:[^"]+)"',
                r'"play[^"]*":"(https:[^"]+)"',
            ]:
                match = re.search(regex, html)
                if match:
                    return match.group(1) if len(match.groups()) else match.group(0)
        except:
            pass
    return video_url

# ---------------------------------------------------------
# HELPERS FFMPEG
# ---------------------------------------------------------
def ffmpeg_installed():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False

def transcode_to_h264_aac(input_path: str, output_path: str) -> bool:
    """
    Re-encode input_path to H.264 + AAC MP4 with faststart and fragmentation flags.
    Returns True on success, False otherwise.
    """
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i", input_path,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "faststart+frag_keyframe+empty_moov",
            "-vf", "scale='min(1920,iw)':'min(1920,ih)':force_original_aspect_ratio=decrease",
            output_path
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        return True
    except Exception as e:
        print("ffmpeg transcode error:", e)
        return False

# ---------------------------------------------------------
# DOWNLOAD HANDLER (com re-encode fallback)
# ---------------------------------------------------------
async def baixar_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    uid = update.message.from_user.id

    if not url.startswith("http"):
        return await update.message.reply_text("❌ Envie um link válido.")

    verificar_pagamentos_asaas()

    if uid not in USUARIOS_PREMIUM:
        usos = verificar_limite(uid)
        if usos >= LIMITE_DIARIO:
            return await update.message.reply_text("⚠️ Limite diário atingido.")

    if "shopee.com" in url or "shp.ee" in url or "sv.shopee.com" in url:
        await update.message.reply_text("🔄 Processando link da Shopee...")
        video_url = extrair_video_shopee(url)
        if not video_url:
            return await update.message.reply_text("❌ Não foi possível extrair vídeo.")
        url = video_url

    await update.message.reply_text("⏳ Baixando...")

    try:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        output_template = str(DOWNLOADS_DIR / f"%(id)s-{timestamp}.%(ext)s")

        # Use minimal postprocessing in yt_dlp; we'll transcode proactively for IG/TikTok
        ydl_opts = {
            "outtmpl": output_template,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "noplaylist": True,
            # ensure ffmpeg tools used by yt_dlp for merging if available
            "postprocessor_args": ["-movflags", "faststart"],
        }

        if COOKIES_TIKTOK.exists():
            ydl_opts["cookiefile"] = str(COOKIES_TIKTOK)

        def run_download(u):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(u, download=True)
                # prepare_filename returns final path including ext
                return ydl.prepare_filename(info)

        loop = asyncio.get_running_loop()
        file_path = await loop.run_in_executor(None, lambda: run_download(url))

        # tiny pause to let FS settle
        await asyncio.sleep(0.3)

        if not os.path.exists(file_path) or os.path.getsize(file_path) < 1024:
            await update.message.reply_text("❌ Erro: arquivo final inválido.")
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
            return

        # Decide whether to transcode:
        # Heuristic: if source is from instagram or tiktok, do re-encode to maximize iPhone compatibility.
        needs_transcode = False
        lower_url = url.lower()
        if "instagram.com" in lower_url or "instagr.am" in lower_url or "tiktok.com" in lower_url or "vt.tiktok.com" in lower_url:
            needs_transcode = True

        final_path = file_path
        transcoded_path = None

        if needs_transcode and ffmpeg_installed():
            # create transcoded filename
            base = os.path.splitext(file_path)[0]
            transcoded_path = f"{base}-h264.mp4"
            success = await asyncio.get_running_loop().run_in_executor(None, lambda: transcode_to_h264_aac(file_path, transcoded_path))
            if success and os.path.exists(transcoded_path) and os.path.getsize(transcoded_path) > 1024:
                final_path = transcoded_path
                # remove original to save space
                try:
                    os.remove(file_path)
                except:
                    pass
            else:
                # fallback: keep original
                final_path = file_path
                try:
                    if transcoded_path and os.path.exists(transcoded_path):
                        os.remove(transcoded_path)
                except:
                    pass

        # Send as video with streaming support
        try:
            with open(final_path, "rb") as f:
                await update.message.reply_video(f, caption="✅ Seu vídeo está aqui!", supports_streaming=True)
        except Exception as e_send:
            # If sending as video fails, try sending as document
            print("Erro ao enviar como video, tentando enviar como documento:", e_send)
            try:
                with open(final_path, "rb") as f:
                    await update.message.reply_document(f, caption="✅ Seu vídeo está aqui (document).")
            except Exception as e_doc:
                print("Erro ao enviar como documento:", e_doc)
                await update.message.reply_text("❌ Falha ao enviar o arquivo. Tente novamente mais tarde.")
                # don't delete files in this critical failure case; keep logs
                return

        # cleanup
        try:
            if final_path and os.path.exists(final_path):
                os.remove(final_path)
            # if transcoded created separately it was removed above or is same as final_path
        except:
            pass

        if uid not in USUARIOS_PREMIUM:
            novo = incrementar_download(uid)
            await update.message.reply_text(f"📊 Uso: {novo}/{LIMITE_DIARIO}")

    except Exception as e:
        traceback.print_exc()
        await update.message.reply_text(f"❌ Erro ao baixar: {e}")

# ---------------------------------------------------------
# MAIN (WEBHOOK)
# ---------------------------------------------------------
async def main():
    verificar_pagamentos_asaas()
    app = Application.builder().token(TOKEN).build()

    async def set_commands(app):
        await app.bot.set_my_commands([
            BotCommand("start", "Iniciar bot"),
            BotCommand("planos", "Planos premium"),
            BotCommand("duvida", "Ajuda"),
            BotCommand("meuid", "Mostrar ID"),
            BotCommand("addpremium", "Adicionar premium (admin)"),
            BotCommand("delpremium", "Remover premium (admin)"),
        ])
    app.post_init = set_commands

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("planos", planos))
    app.add_handler(CommandHandler("duvida", duvida))
    app.add_handler(CommandHandler("meuid", meuid))
    app.add_handler(CommandHandler("addpremium", addpremium))
    app.add_handler(CommandHandler("delpremium", delpremium))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, baixar_video))

    print(f"Iniciando bot (webhook) na porta {PORT}...")
    await app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}/webhook",
    )

# ---------------------------------------------------------
# EXECUÇÃO SEGURA PARA RENDER
# ---------------------------------------------------------
if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
