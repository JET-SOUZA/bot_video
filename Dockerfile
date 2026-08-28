FROM node:20-bookworm-slim AS pot-builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# O plugin bgutil-ytdlp-pot-provider procura automaticamente o script
# em ~/bgutil-ytdlp-pot-provider. No container final, HOME=/root.
RUN git clone --depth 1 --branch 1.3.1 \
    https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
    /root/bgutil-ytdlp-pot-provider

WORKDIR /root/bgutil-ytdlp-pot-provider/server
RUN npm ci && npx tsc

FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PORT=10000

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Node.js/nodejs 20 + BgUtils: geração automática de PO Tokens do YouTube.
COPY --from=pot-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=pot-builder /root/bgutil-ytdlp-pot-provider /root/bgutil-ytdlp-pot-provider

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
RUN mkdir -p /app/downloads && chmod -R a+rw /app/downloads

CMD ["python", "jetbot_v2.py"]
