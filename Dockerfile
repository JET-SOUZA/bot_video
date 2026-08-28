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
    PORT=10000 \
    DENO_VERSION=2.9.5

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates curl unzip && \
    curl -fsSL "https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/deno-x86_64-unknown-linux-gnu.zip" -o /tmp/deno.zip && \
    unzip /tmp/deno.zip -d /usr/local/bin && \
    chmod +x /usr/local/bin/deno && \
    rm -f /tmp/deno.zip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Node 22 atende o runtime EJS atual do yt-dlp; Deno fica disponível como
# runtime recomendado para os desafios JavaScript do YouTube.
COPY --from=pot-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=pot-builder /root/bgutil-ytdlp-pot-provider /root/bgutil-ytdlp-pot-provider

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
RUN mkdir -p /app/downloads && chmod -R a+rw /app/downloads

# Inicializa o servidor local de PO Token e depois a V2.
CMD ["sh", "-c", "node /root/bgutil-ytdlp-pot-provider/server/build/main.js 2>&1 & exec python -c \"import sitecustomize, runpy; runpy.run_path('/app/jetbot_v2.py', run_name='__main__')\""]
