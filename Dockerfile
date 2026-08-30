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

# Start the Node HTTP PO-token provider and only launch JetBot after /ping is live.
# bootstrap_v2.py owns and verifies patch ordering. Diagnostics are opt-in via
# SHOPEE_DIAGNOSTICS=1; marked Shopee media is unconditionally blocked.
CMD ["sh", "-c", "node /root/bgutil-ytdlp-pot-provider/server/build/main.js >/tmp/bgutil.log 2>&1 & i=0; until curl -fsS http://127.0.0.1:4416/ping >/dev/null; do i=$((i+1)); [ $i -lt 100 ] || { cat /tmp/bgutil.log; exit 1; }; sleep .2; done; exec python /app/bootstrap_v2.py"]
