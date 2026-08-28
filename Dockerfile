FROM node:22-bookworm-slim AS pot-builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

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

COPY --from=pot-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=pot-builder /root/bgutil-ytdlp-pot-provider /root/bgutil-ytdlp-pot-provider

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
RUN mkdir -p /app/downloads && chmod -R a+rw /app/downloads

# Start the Node HTTP PO-token provider and only launch the bot after /ping is live.
# Runtime patches preserve X/Twitter geometry, fit only oversized Telegram files,
# keep YouTube auth errors concise, and isolate staged Shopee probes from main.
CMD ["sh", "-c", "node /root/bgutil-ytdlp-pot-provider/server/build/main.js >/tmp/bgutil.log 2>&1 & i=0; until curl -fsS http://127.0.0.1:4416/ping >/dev/null; do i=$((i+1)); [ $i -lt 100 ] || { cat /tmp/bgutil.log; exit 1; }; sleep .2; done; exec python -c \"import shopee_diag_capture, sitecustomize, shopee_structured_patch, shopee_sourcemap_probe, shopee_frontend_api_patch, shopee_timeline_patch, media_fidelity_patch, telegram_fit_patch, youtube_auth_patch, shopee_diag_telegram_patch, runpy; runpy.run_path('/app/run_v2_fallback.py', run_name='__main__')\""]
