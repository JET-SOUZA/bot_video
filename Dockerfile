# Dockerfile — place na raiz do repositório
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PORT=10000

# Instala ffmpeg e dependências básicas
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ffmpeg \
      build-essential \
      ca-certificates \
      git \
      wget && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Criar pasta da app
WORKDIR /app

# Copia requirements se existir (melhora cache)
COPY requirements.txt /app/requirements.txt

# Instala dependências Python (se houver requirements.txt)
RUN if [ -f /app/requirements.txt ]; then pip install --no-cache-dir -r /app/requirements.txt; fi

# Copia todo o projeto
COPY . /app

# Garante permissões (opcional)
RUN mkdir -p /app/downloads && chmod -R a+rw /app/downloads

# Comando padrão (ajuste se usar outro)
CMD ["python", "bot.py"]
