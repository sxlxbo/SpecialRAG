# ── doc-rag one-time setup (Windows PowerShell) ────────────────────────
# Usage: .\setup.ps1

$ErrorActionPreference = "Stop"
Write-Host "=== doc-rag setup ===" -ForegroundColor Cyan

# 1. Prerequisites
Write-Host "[1/5] Checking prerequisites..." -ForegroundColor Yellow
$pyVer = python --version 2>&1
if ($pyVer -notmatch "3\.(11|12)") {
    Write-Host "ERROR: Python 3.11+ required. Current: $pyVer" -ForegroundColor Red
    exit 1
}
Write-Host "  OK: $pyVer"

try { uv --version | Out-Null }
catch {
    Write-Host "Installing uv..." -ForegroundColor Yellow
    pip install uv
}

# 2. Python deps
Write-Host "[2/5] Installing Python dependencies..." -ForegroundColor Yellow
uv sync

# 3. WebUI
if (Test-Path "nanobot-main/nanobot/web/dist/index.html") {
    Write-Host "[3/5] WebUI already built — skipping." -ForegroundColor Yellow
}
else {
    Write-Host "[3/5] Building WebUI..." -ForegroundColor Yellow
    if (Get-Command bun -ErrorAction SilentlyContinue) {
        Push-Location nanobot-main/webui
        bun install --frozen-lockfile
        bun run build
        Pop-Location
    }
    elseif (Get-Command npm -ErrorAction SilentlyContinue) {
        Push-Location nanobot-main/webui
        npm ci
        npm run build
        Pop-Location
    }
    else {
        Write-Host "WARNING: bun/npm not found — WebUI unavailable." -ForegroundColor Red
    }
}

# 4. Config
Write-Host "[4/5] Setting up nanobot config..." -ForegroundColor Yellow
$ConfigDir = "$env:USERPROFILE\.nanobot"
$ConfigFile = "$ConfigDir\config.json"
if (-not (Test-Path $ConfigFile)) {
    New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
    @'
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
'@ | Set-Content -Path $ConfigFile
    Write-Host "  Created: $ConfigFile"
}
else {
    Write-Host "  Already exists: $ConfigFile"
}

# 5. Verify
Write-Host "[5/5] Verifying..." -ForegroundColor Yellow
uv run python -c "from doc_rag.chunk_store import ChunkStore; print('  OK: doc_rag')"
uv run python -c "from nanobot.nanobot import Nanobot; print('  OK: nanobot')"

Write-Host ""
Write-Host "=== Setup complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Set API key:  `$env:OPENAI_API_KEY='sk-...'"
Write-Host "  2. Index a PDF:  uv run doc-index --pdf \path\to\doc.pdf"
Write-Host "  3. Start:        uv run doc-gateway"
Write-Host "  4. Open:         http://127.0.0.1:8765"
