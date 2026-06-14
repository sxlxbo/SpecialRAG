# ── Stage 1: Build nanobot WebUI frontend ────────────────────────────
FROM oven/bun:1-alpine AS webui-builder
WORKDIR /build/webui

COPY nanobot-main/webui/package.json nanobot-main/webui/bun.lock ./
RUN bun install --frozen-lockfile

COPY nanobot-main/webui/ ./
RUN bun run build


# ── Stage 2: Python dependencies + app ────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.11-bookworm AS builder

ENV UV_COMPILE_BYTECODE=1
WORKDIR /build

# Create venv and install all packages
RUN uv venv /build/.venv

# Copy PageIndex source
COPY PageIndex-main/pyproject.toml PageIndex-main/
COPY PageIndex-main/pageindex/      PageIndex-main/pageindex/
COPY PageIndex-main/requirements.txt PageIndex-main/

# Copy nanobot source (without webui dist yet)
COPY nanobot-main/pyproject.toml nanobot-main/
COPY nanobot-main/nanobot/       nanobot-main/nanobot/

# Copy our package source
COPY pyproject.toml .python-version ./
COPY src/ src/

# Install in order: PageIndex first, then nanobot, then our package
RUN uv pip install \
    --python /build/.venv/bin/python \
    "./PageIndex-main" \
    "./nanobot-main" \
    ".[api]"

# Copy built WebUI into nanobot package
COPY --from=webui-builder /build/webui/dist/ nanobot-main/nanobot/web/dist/


# ── Stage 3: Runtime ──────────────────────────────────────────────────
FROM python:3.11-slim-bookworm

RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash docrag

WORKDIR /app

# Copy venv from builder
COPY --from=builder --chown=docrag:docrag /build/.venv /app/.venv

# Copy full source (needed for skill files, templates, pageindex utils at runtime)
COPY --chown=docrag:docrag PageIndex-main/ PageIndex-main/
COPY --chown=docrag:docrag nanobot-main/ nanobot-main/
COPY --chown=docrag:docrag src/ src/
COPY --chown=docrag:docrag skills/ skills/
COPY --chown=docrag:docrag pyproject.toml ./

# Copy entrypoint
COPY --chown=docrag:docrag docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Wire doc_tools into nanobot's auto-discovery path
RUN cp src/doc_rag/nanobot_doc_tools.py nanobot-main/nanobot/agent/tools/doc_tools.py \
    && cp -r skills/document-qa nanobot-main/nanobot/skills/

# Runtime directories
RUN mkdir -p /app/doc_workspace /home/docrag/.nanobot \
    && chown -R docrag:docrag /app /home/docrag/.nanobot

VOLUME ["/app/doc_workspace", "/home/docrag/.nanobot"]

USER docrag
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DOC_WORKSPACE=/app/doc_workspace

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:8765/api/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
