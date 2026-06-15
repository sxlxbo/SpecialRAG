"""
CLI entry points for doc-rag: index documents and start the gateway.
Registered in pyproject.toml as [project.scripts].
"""

import argparse
import json
import os
import sys
from pathlib import Path

from .chunk_store import ChunkStore


def _resolve_workspace(workspace: str | None) -> str:
    return os.path.abspath(workspace or os.getenv("DOC_WORKSPACE", "./doc_workspace"))


def index_main():
    """Entry point: doc-index --pdf /path/to/doc.pdf"""
    parser = argparse.ArgumentParser(description="Index a document for RAG")
    parser.add_argument("--pdf", type=str, help="Path to PDF file")
    parser.add_argument("--md", type=str, help="Path to Markdown file")
    parser.add_argument("--workspace", type=str, default=None,
                        help="Workspace dir (env: DOC_WORKSPACE, default: ./doc_workspace)")
    parser.add_argument("--model", type=str, default=None,
                        help="LLM model (e.g. openai/gpt-4o-mini)")
    parser.add_argument("--api-key", type=str, default=None,
                        help="API key (or set OPENAI_API_KEY env var)")
    args = parser.parse_args()

    if not args.pdf and not args.md:
        parser.error("Either --pdf or --md is required")

    file_path = args.pdf or args.md
    if not os.path.isfile(file_path):
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "PageIndex-main"))
    from pageindex import PageIndexClient

    workspace = _resolve_workspace(args.workspace)
    os.makedirs(workspace, exist_ok=True)

    print(f"Indexing: {file_path}")
    client = PageIndexClient(api_key=args.api_key, model=args.model, workspace=workspace)
    doc_id = client.index(file_path)

    # Verify chunks are loadable
    store = ChunkStore(workspace)
    store.load_workspace()
    print(f"Done. doc_id={doc_id}")
    print(f"Chunks: {store.stats()}")


def gateway_main():
    """Entry point: doc-gateway"""
    parser = argparse.ArgumentParser(description="Start doc-rag gateway with nanobot WebUI")
    parser.add_argument("--workspace", type=str, default=None,
                        help="Workspace dir (env: DOC_WORKSPACE, default: ./doc_workspace)")
    parser.add_argument("--host", type=str, default=None,
                        help="Gateway host (env: GATEWAY_HOST, default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None,
                        help="Gateway port (env: GATEWAY_PORT, default: 8765)")
    args = parser.parse_args()

    workspace = _resolve_workspace(args.workspace)
    host = args.host or os.getenv("GATEWAY_HOST", "127.0.0.1")
    port = args.port or int(os.getenv("GATEWAY_PORT", "8765"))

    # Validate workspace
    store = ChunkStore(workspace)
    store.load_workspace()
    if store.stats()["documents"] == 0:
        print(f"Warning: no documents in workspace '{workspace}' — "
              f"run 'doc-index --pdf <file>' first.")
    else:
        print(f"Workspace loaded: {store.stats()}")

    # Register tools and start gateway
    print(f"Starting gateway on {host}:{port} ...")
    print("Use Ctrl+C to stop.")

    # The nanobot gateway reads config from ~/.nanobot/config.json
    # and auto-discovers tools from nanobot/agent/tools/.
    # Our doc_tools.py has been placed there, so they register automatically.
    # Set env vars so nanobot picks them up:
    os.environ.setdefault("DOC_WORKSPACE", workspace)

    from nanobot.config.loader import load_config, resolve_config_env_vars
    from nanobot.cli.commands import _run_gateway

    cfg = resolve_config_env_vars(load_config())
    cfg.gateway.host = host
    cfg.gateway.port = port
    _run_gateway(cfg, port=port, health_server_enabled=False)
