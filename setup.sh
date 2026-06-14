#!/bin/bash
# ── doc-rag one-time setup ──────────────────────────────────────────────
# Usage: bash setup.sh
set -e

echo "=== doc-rag setup ==="

# 1. Check prerequisites
echo "[1/5] Checking prerequisites..."
python --version 2>&1 | grep -q "3.11\|3.12" || {
    echo "ERROR: Python 3.11+ required. Current: $(python --version)"
    exit 1
}

uv --version >/dev/null 2>&1 || {
    echo "Installing uv..."
    pip install uv
}

# 2. Install Python dependencies
echo "[2/5] Installing Python dependencies (uv sync)..."
uv sync

# 3. Build WebUI (skip if pre-built dist exists)
if [ -f "nanobot-main/nanobot/web/dist/index.html" ]; then
    echo "[3/5] WebUI already built — skipping."
else
    echo "[3/5] Building WebUI..."
    if command -v bun &>/dev/null; then
        cd nanobot-main/webui && bun install --frozen-lockfile && bun run build && cd ../..
    elif command -v npm &>/dev/null; then
        cd nanobot-main/webui && npm ci && npm run build && cd ../..
    else
        echo "WARNING: neither bun nor npm found — WebUI will not be available."
        echo "  Install bun (https://bun.sh) or npm and re-run: bash setup.sh"
    fi
fi

# 4. Initialize nanobot config
echo "[4/5] Setting up nanobot config..."
CONFIG_DIR="${HOME}/.nanobot"
CONFIG_FILE="${CONFIG_DIR}/config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    mkdir -p "$CONFIG_DIR"
    cat > "$CONFIG_FILE" << 'ENDCONFIG'
{
  "agents": {
    "defaults": {
      "model": "openai/gpt-4o-mini",
      "provider": "openai",
      "workspace": "./doc_workspace"
    }
  },
  "providers": {
    "openai": {}
  },
  "gateway": {
    "host": "127.0.0.1",
    "port": 8765
  }
}
ENDCONFIG
    echo "  Created: ${CONFIG_FILE}"
else
    echo "  Already exists: ${CONFIG_FILE}"
fi

# 5. Verify
echo "[5/5] Verifying..."
uv run python -c "from doc_rag.chunk_store import ChunkStore; print('  OK: doc_rag module loads')" || {
    echo "ERROR: doc_rag import failed"
    exit 1
}
uv run python -c "from nanobot.nanobot import Nanobot; print('  OK: nanobot module loads')" || {
    echo "ERROR: nanobot import failed"
    exit 1
}

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Set API key:  export OPENAI_API_KEY=sk-..."
echo "  2. Index a PDF:  uv run doc-index --pdf /path/to/doc.pdf"
echo "  3. Start:        uv run doc-gateway"
echo "  4. Open:         http://127.0.0.1:8765"
