# Ryu — issue tracker onde agentes de IA são membros da equipe
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1

# Dependências de sistema: git e curl (sem nodejs/npm; as CLIs de agente
# rodam no Daemon, na máquina do usuário, e não no container do servidor).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

# uv (instalador Python rápido)
RUN pip install --no-cache-dir uv

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
