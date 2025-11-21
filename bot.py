# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
async def main():
    # Carregamentos iniciais
    verificar_pagamentos_asaas()
    load_youtube_cookies_from_env()

    # Inicializa aplicação
    app = Application.builder().token(TOKEN).build()

    # -----------------------------------------------------
    # COMANDOS
    # -----------------------------------------------------
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addpremium", addpremium))
    app.add_handler(CommandHandler("delpremium", delpremium))
    app.add_handler(CommandHandler("verpremium", verpremium))
    app.add_handler(CommandHandler("meuid", meuid))
    app.add_handler(CommandHandler("planos", planos))   # <--- CORRIGIDO

    # -----------------------------------------------------
    # Botão "Planos" no teclado (reply keyboard)
    # -----------------------------------------------------
    app.add_handler(
        MessageHandler(
            filters.Regex(r'^(Planos|💎 Planos)$'),
            planos
        )
    )

    # -----------------------------------------------------
    # MENSAGENS DE TEXTO PARA DOWNLOAD
    # -----------------------------------------------------
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            baixar_video
        )
    )

    # -----------------------------------------------------
    # CALLBACKS (Inline Buttons)
    # -----------------------------------------------------
    app.add_handler(CallbackQueryHandler(callbacks_handler))

    # -----------------------------------------------------
    # KEEPALIVE AUTOMÁTICO
    # -----------------------------------------------------
    asyncio.create_task(keepalive_task())

    # -----------------------------------------------------
    # EXECUÇÃO: WEBHOOK (Render) ou POLLING (local)
    # -----------------------------------------------------
    port = PORT
    url = os.environ.get("RENDER_EXTERNAL_URL")

    if not url:
        print("Rodando LOCAL (Polling)...")
        await app.run_polling()
        return

    print(f"Iniciando bot (webhook) na porta {port}...")
    await app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=TOKEN,
        webhook_url=f"{url}/{TOKEN}",
    )


# ---------------------------------------------------------
# RUN
# ---------------------------------------------------------
if __name__ == "__main__":
    import nest_asyncio  # <--- IMPORTAÇÃO CORRETA
    nest_asyncio.apply()
    asyncio.run(main())

