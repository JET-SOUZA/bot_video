FROM node:22-bookworm-slim AS pot-builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Provider recomendado pelo ecossistema yt-dlp para gerar PO Tokens
# automaticamente em IPs de datacenter (como Render).
RUN git clone --depth 1 --branch 1.3.1 \
    https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
    /root/bgutil-ytdlp-pot-provider

WORKDIR /root/bgutil-ytdlp-pot-provider/server
RUN npm ci && npx tsc

FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=10000

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Node 22 atende o runtime JavaScript atual do yt-dlp e também executa o
# servidor HTTP do BgUtils. Deno foi removido desta imagem porque, quando o
# servidor HTTP falhava, o provider podia cair no script Deno e estourar o
# timeout fixo de 15 s antes mesmo do download começar.
COPY --from=pot-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=pot-builder /root/bgutil-ytdlp-pot-provider /root/bgutil-ytdlp-pot-provider

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
RUN mkdir -p /app/downloads && chmod -R a+rw /app/downloads

# O BgUtils sobe primeiro e o bot só inicia depois que /ping responder. Isso
# força o caminho HTTP (mais rápido/recomendado pelo projeto) a estar disponível
# antes de qualquer tentativa de YouTube. A V2 também carrega a preservação de
# mídia do X/Twitter e as camadas atuais de investigação da Shopee.
CMD ["sh", "-c", "node /root/bgutil-ytdlp-pot-provider/server/build/main.js 2>&1 & POT_PID=$!; i=0; until curl -fsS http://127.0.0.1:4416/ping >/dev/null 2>&1; do i=$((i+1)); if [ $i -ge 100 ]; then echo '[JetBot YT] BgUtils HTTP server failed readiness check'; kill $POT_PID 2>/dev/null || true; exit 1; fi; sleep 0.2; done; echo '[JetBot YT] BgUtils HTTP server ready'; exec python -c \"import shopee_diag_capture, sitecustomize, media_fidelity_patch, shopee_structured_patch, shopee_sourcemap_probe, shopee_frontend_api_patch, shopee_timeline_patch, shopee_diag_telegram_patch, runpy; runpy.run_path('/app/run_v2_fallback.py', run_name='__main__')\""]
