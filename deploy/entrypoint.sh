#!/bin/sh
set -e

# Diretórios persistentes (volume /data)
mkdir -p /data /data/workspaces /data/uploads

exec uvicorn ryu.main:app --host 0.0.0.0 --port "${RYU_PORT:-8000}"
