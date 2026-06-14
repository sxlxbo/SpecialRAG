#!/usr/bin/env python3
"""
Start nanobot gateway with document RAG tools registered.

Usage:
    # Set API keys
    export OPENAI_API_KEY=sk-...

    # First index a document
    python run_index.py --pdf /path/to/doc.pdf --workspace ./doc_workspace

    # Then start the gateway
    python run_gateway.py --workspace ./doc_workspace
    python run_gateway.py --workspace ./doc_workspace --config ~/.nanobot/config.json

This script:
1. Loads PageIndex workspace chunks
2. Creates the nanobot agent loop
3. Registers doc_list, doc_structure, doc_search, doc_chunk tools
4. Starts the gateway with WebUI
"""

import argparse
import os
import sys
from pathlib import Path

# Add dependencies to path
_SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR / "nanobot-main"))

from doc_rag.chunk_store import ChunkStore
from doc_rag.tools import DocListTool, DocStructureTool, DocSearchTool, DocChunkTool, init_store


def register_doc_tools(loop, workspace_dir: str) -> list[str]:
    """Register document RAG tools with an AgentLoop's ToolRegistry."""
    init_store(workspace_dir)
    tools = [DocListTool(), DocStructureTool(), DocSearchTool(), DocChunkTool()]
    registered = []
    for tool in tools:
        loop.tools.register(tool)
        registered.append(tool.name)
    return registered


def main():
    parser = argparse.ArgumentParser(
        description="Start nanobot gateway with document RAG tools"
    )
    parser.add_argument("--workspace", type=str, default="./doc_workspace",
                        help="Document workspace directory (default: ./doc_workspace)")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to nanobot config.json (default: ~/.nanobot/config.json)")
    parser.add_argument("--port", type=int, default=8765,
                        help="Gateway port (default: 8765)")
    parser.add_argument("--host", type=str, default="127.0.0.1",
                        help="Gateway host (default: 127.0.0.1)")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    if not workspace.exists() or not (workspace / "_meta.json").exists():
        print(f"Warning: Workspace {workspace} has no _meta.json. "
              f"Run 'python run_index.py --pdf <file> --workspace {workspace}' first.")
        print("Continuing with empty store...")

    # Initialize chunk store
    store = init_store(str(workspace))
    print(f"Loaded workspace: {store.stats()}")

    # Create nanobot instance
    from nanobot.nanobot import Nanobot
    from nanobot.config.loader import load_config, resolve_config_env_vars

    config = resolve_config_env_vars(load_config(args.config))
    # Override host/port in config
    config.gateway.host = args.host
    config.gateway.port = args.port

    bot = Nanobot.from_config(config_path=None, workspace=str(workspace))
    register_doc_tools(bot._loop, str(workspace))
    print(f"Registered document tools: {bot.tool_names}")

    # The Nanobot SDK creates the loop but doesn't start the gateway.
    # For the gateway + WebUI, we need to start it via the gateway module.
    print(f"\n[info] To start the full gateway with WebUI, use the nanobot CLI:")
    print(f"  cd nanobot-main && pip install -e .")
    print(f"  cp doc_rag/agent/tools/doc_tools.py nanobot-main/nanobot/agent/tools/")
    print(f"  nanobot gateway")
    print(f"\n[info] Or run the agent in programmatic mode:\n")

    import asyncio

    async def demo():
        print("=" * 60)
        print("Document RAG agent ready. Type a question (or 'quit'):")
        print(f"Available documents: {len(store.list_documents())}")
        for doc in store.list_documents():
            print(f"  [{doc['doc_id']}] {doc['doc_name']}")
        print("=" * 60)

        while True:
            try:
                question = input("\n> ")
                if question.lower() in ("quit", "exit", "q"):
                    break
                result = await bot.run(question)
                print(f"\n{result.content}")
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")

    asyncio.run(demo())


if __name__ == "__main__":
    main()
