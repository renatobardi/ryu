# Ryu — issue tracker onde agentes de IA são membros da equipe
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1

# Dependências de sistema: nodejs+npm (CLIs de agente), git e curl
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates git nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# uv (instalador Python rápido)
RUN pip install --no-cache-dir uv

# CLIs de agente. Se o npm falhar (rede/registry), o build segue —
# os adapters do Ryu têm fallback quando o binário não existe.
RUN npm install -g @anthropic-ai/claude-code @openai/codex || \
    echo "WARN: npm install das CLIs de agente falhou; seguindo sem (adapters usam fallback)"

WORKDIR /app

# Instala o projeto
COPY pyproject.toml ./
COPY src ./src
RUN uv pip install --system .

# Entrypoint
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
VOLUME ["/data"]

ENTRYPOINT ["/entrypoint.sh"]
