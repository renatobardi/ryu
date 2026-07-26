#!/usr/bin/env bash
set -euo pipefail

# ryu-up.sh — install/upgrade Ryu from GHCR on any machine with Docker.
# Idempotent: re-run to update the image tag without losing data.

IMAGE_ROOT="ghcr.io/renatobardi/ryu"
CONTAINER_NAME="ryu"
SECRET_DIR="${HOME}/.config/ryu"
SECRET_FILE="${SECRET_DIR}/secret"

PORT="8800"
TAG="latest"
VOLUME="ryu_data"
ENV_FILE=""

usage() {
  cat <<EOF
Uso: bash deploy/ryu-up.sh [flags]

Flags:
  --port <n>         Porta no host (default: 8800)
  --tag <tag>        Tag da imagem no GHCR (default: latest)
  --data-volume <v>  Nome do volume/pasta do Docker (default: ryu_data)
  --env-file <path>  Arquivo .env extra com variáveis RYU_* (default: ./ryu.env se existir)
  -h, --help         Exibe esta ajuda
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --port)
      [ -n "${2:-}" ] || { echo "--port requer um valor" >&2; usage >&2; exit 1; }
      PORT="$2"
      shift 2
      ;;
    --tag)
      [ -n "${2:-}" ] || { echo "--tag requer um valor" >&2; usage >&2; exit 1; }
      TAG="$2"
      shift 2
      ;;
    --data-volume)
      [ -n "${2:-}" ] || { echo "--data-volume requer um valor" >&2; usage >&2; exit 1; }
      VOLUME="$2"
      shift 2
      ;;
    --env-file)
      [ -n "${2:-}" ] || { echo "--env-file requer um caminho" >&2; usage >&2; exit 1; }
      ENV_FILE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Opção desconhecida: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

# Default env-file: ./ryu.env if it exists and the user did not override.
if [ -z "$ENV_FILE" ] && [ -f "./ryu.env" ]; then
  ENV_FILE="./ryu.env"
fi

# Validate port is a number.
case "$PORT" in
  *[!0-9]*)
    echo "Porta inválida: $PORT" >&2
    exit 1
    ;;
esac

if [ "$PORT" -le 0 ] || [ "$PORT" -gt 65535 ]; then
  echo "Porta fora do intervalo válido (1-65535): $PORT" >&2
  exit 1
fi

for cmd in docker curl openssl; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Comando necessário não encontrado: $cmd" >&2
    exit 1
  fi
done

ensure_secret() {
  mkdir -p "$SECRET_DIR"
  if [ -f "$SECRET_FILE" ]; then
    # Reuse existing secret; never overwrite.
    JWT_SECRET="$(sed -n 's/^RYU_JWT_SECRET=//p' "$SECRET_FILE" | head -n 1)"
    if [ -z "$JWT_SECRET" ]; then
      echo "Arquivo de secret vazio ou malformado: $SECRET_FILE" >&2
      exit 1
    fi
  else
    JWT_SECRET="$(openssl rand -hex 32)"
    printf 'RYU_JWT_SECRET=%s\n' "$JWT_SECRET" > "$SECRET_FILE"
    chmod 600 "$SECRET_FILE"
  fi
}

ensure_secret

IMAGE="${IMAGE_ROOT}:${TAG}"

echo "==> Pulling image ${IMAGE}..."
docker pull "$IMAGE"

echo "==> Stopping old container (if any)..."
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

echo "==> Starting container ${CONTAINER_NAME}..."
RUN_ARGS=(
  -d
  --name "$CONTAINER_NAME"
  --restart unless-stopped
  -v "${VOLUME}:/data"
  -p "127.0.0.1:${PORT}:8000"
  -e "RYU_JWT_SECRET=${JWT_SECRET}"
)

if [ -n "$ENV_FILE" ]; then
  if [ ! -f "$ENV_FILE" ]; then
    echo "Env file não encontrado: $ENV_FILE" >&2
    exit 1
  fi
  # If the user env-file sets RYU_JWT_SECRET, it is overridden by the explicit -e above.
  RUN_ARGS+=(--env-file "$ENV_FILE")
fi

RUN_ARGS+=("$IMAGE")

docker run "${RUN_ARGS[@]}"

echo "==> Waiting for /healthz..."
HEALTH_URL="http://127.0.0.1:${PORT}/healthz"
READY=0
for i in $(seq 0 30); do
  if curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 1
done

if [ "$READY" -ne 1 ]; then
  echo "Erro: healthcheck falhou após 30s. Logs do container:" >&2
  docker logs --tail 30 "$CONTAINER_NAME" >&2 || true
  exit 1
fi

echo
echo "Ryu está rodando em: http://127.0.0.1:${PORT}"
echo
echo "Para fazer o primeiro login:"
echo "  1. Acesse http://127.0.0.1:${PORT}"
echo "  2. Digite seu e-mail na tela de login."
echo "  3. Veja o código de 6 dígitos no log:"
echo "     docker logs -f ${CONTAINER_NAME}"
echo
