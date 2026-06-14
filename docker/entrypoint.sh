#!/bin/bash
set -e

CONFIG_DIR="${HOME}/.nanobot"
CONFIG_FILE="${CONFIG_DIR}/config.json"

# ── First run: seed a minimal nanobot config ────────────────────────────
if [ ! -f "$CONFIG_FILE" ]; then
    echo "[entrypoint] Creating default config at ${CONFIG_FILE}"
    mkdir -p "$CONFIG_DIR"

    cat > "$CONFIG_FILE" << 'ENDCONFIG'
{
  "agents": {
    "defaults": {
      "model": "openai/gpt-4o-mini",
      "provider": "openai",
      "workspace": "/app/doc_workspace"
    }
  },
  "providers": {
    "openai": {}
  },
  "gateway": {
    "host": "0.0.0.0",
    "port": 8765
  }
}
ENDCONFIG

    echo "[entrypoint] Default config written."
    echo "[entrypoint] Edit via volume mount: docker compose exec gateway vi ~/.nanobot/config.json"
fi

# ── Ensure workspace exists ─────────────────────────────────────────────
mkdir -p "${DOC_WORKSPACE:-/app/doc_workspace}"

# ── Pre-flight checks ───────────────────────────────────────────────────
if [ -z "$OPENAI_API_KEY" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "[entrypoint] ⚠ WARNING: No API key found. Set OPENAI_API_KEY or ANTHROPIC_API_KEY."
    echo "[entrypoint]   docker compose run --rm -e OPENAI_API_KEY=sk-... gateway"
fi

echo "[entrypoint] Workspace: ${DOC_WORKSPACE:-/app/doc_workspace}"
echo "[entrypoint] Config:    ${CONFIG_FILE}"
echo "[entrypoint] Starting nanobot gateway..."

exec nanobot gateway
