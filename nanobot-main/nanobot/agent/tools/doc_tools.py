"""
Nanobot tools for document RAG: doc_list, doc_structure, doc_search, doc_chunk.

Placement: copy/symlink into nanobot-main/nanobot/agent/tools/doc_tools.py
so nanobot's ToolLoader auto-discovers the tools on gateway boot.

Environment:
    DOC_WORKSPACE   path to the PageIndex workspace directory (default: ./doc_workspace)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# ── Resolve doc_rag import ──────────────────────────────────────────────
# The tools file lives in nanobot/agent/tools/ but needs to import doc_rag.
# We try several resolution strategies in order:
#   1. DOC_RAG_PATH env var (explicit override)
#   2. src/doc_rag relative to cwd (Docker/production layout)
#   3. doc_rag relative to cwd (dev layout)
#   4. Search upward from __file__

_FOUND = False
for _candidate_dir in filter(None, [
    os.getenv("DOC_RAG_PATH"),
    str(Path.cwd() / "src"),
    str(Path.cwd()),
    *[str(p) for p in Path(__file__).resolve().parents[:6]],
]):
    _test = Path(_candidate_dir) / "doc_rag" / "chunk_store.py"
    if _test.exists():
        if _candidate_dir not in sys.path:
            sys.path.insert(0, _candidate_dir)
        _FOUND = True
        break

if not _FOUND:
    raise ImportError(
        "Cannot find doc_rag package. Set DOC_RAG_PATH env var to the directory "
        "containing doc_rag/ (e.g. /app/src or /app)."
    )

from doc_rag.chunk_store import ChunkStore  # noqa: E402
from nanobot.agent.tools.base import Tool, tool_parameters  # noqa: E402

# ── Singleton store ──────────────────────────────────────────────────────

_store: ChunkStore | None = None


def _get_workspace() -> str:
    return os.getenv("DOC_WORKSPACE", "./doc_workspace")


def init_store(workspace: str | None = None):
    """Initialize (or re-initialize) the global chunk store."""
    global _store
    ws = workspace or _get_workspace()
    _store = ChunkStore(ws)
    _store.load_workspace()
    return _store


def _get_store() -> ChunkStore:
    global _store
    if _store is None:
        _store = init_store()
    return _store


# ── Tool: doc_list ────────────────────────────────────────────────────────

@tool_parameters({"type": "object", "properties": {}, "required": []})
class DocListTool(Tool):
    name = "doc_list"
    description = (
        "List all available indexed documents. Returns each document's id, "
        "name, and a short description. Call this FIRST when a user asks "
        "about document content."
    )

    async def execute(self, **kwargs: Any) -> str:
        try:
            store = _get_store()
            docs = store.list_documents()
            if not docs:
                return json.dumps({
                    "message": "No documents indexed yet.",
                    "hint": "Run: doc-index --pdf /path/to/document.pdf"
                }, ensure_ascii=False)
            return json.dumps(docs, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": f"Failed to list documents: {e}"})


# ── Tool: doc_structure ───────────────────────────────────────────────────

@tool_parameters({
    "type": "object",
    "properties": {
        "doc_id": {
            "type": "string",
            "description": "Document ID returned by doc_list."
        }
    },
    "required": ["doc_id"],
})
class DocStructureTool(Tool):
    name = "doc_structure"
    description = (
        "Get the complete hierarchical table of contents for a document. "
        "Returns each section's title, node_id, page range (start_index/end_index), "
        "and summary. Leaf nodes (no 'nodes' field) are the most granular sections. "
        "Use the returned node_id values with doc_chunk to fetch full section text."
    )

    async def execute(self, doc_id: str, **kwargs: Any) -> str:
        try:
            store = _get_store()
            structure = store.get_document_structure(doc_id)
            if structure is None:
                return json.dumps({
                    "error": f"Document '{doc_id}' not found.",
                    "hint": "Use doc_list to see available document IDs."
                }, ensure_ascii=False)
            return json.dumps(structure, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": f"Failed to get structure: {e}"})


# ── Tool: doc_search ─────────────────────────────────────────────────────

@tool_parameters({
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Keywords or phrase to search for in document sections."
        },
        "doc_id": {
            "type": "string",
            "description": "Optional. Limit search to a specific document ID."
        },
        "top_k": {
            "type": "integer",
            "description": "Max results to return. Default 5, max 10."
        },
    },
    "required": ["query"],
})
class DocSearchTool(Tool):
    name = "doc_search"
    description = (
        "Search document sections by keyword. Returns the top matching leaf-level "
        "sections with their title, full_path, node_id, summary, and page range. "
        "Use this to locate which sections are most relevant to a user's question "
        "before fetching full text via doc_chunk."
    )

    async def execute(self, query: str, doc_id: str = "", top_k: int = 5, **kwargs: Any) -> str:
        try:
            store = _get_store()
            results = store.search(query, top_k=min(top_k, 10), doc_id=doc_id or None)
            if not results:
                return json.dumps({
                    "message": "No matching sections found.",
                    "hint": "Try different keywords or use doc_structure to browse the TOC."
                }, ensure_ascii=False)
            return json.dumps([{
                "title": c.get("title"),
                "node_id": c.get("node_id"),
                "full_path": c.get("full_path"),
                "summary": (c.get("summary") or "")[:300],
                "pages": f"{c.get('start_index')}-{c.get('end_index')}",
            } for c in results], ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": f"Search failed: {e}"})


# ── Tool: doc_chunk ───────────────────────────────────────────────────────

@tool_parameters({
    "type": "object",
    "properties": {
        "doc_id": {
            "type": "string",
            "description": "Document ID."
        },
        "node_id": {
            "type": "string",
            "description": (
                "Section node_id to fetch full text for. "
                "Supports comma-separated list: '0003,0005,0008'."
            )
        },
    },
    "required": ["doc_id", "node_id"],
})
class DocChunkTool(Tool):
    name = "doc_chunk"
    description = (
        "Retrieve the full text of specific document sections by node_id. "
        "Use AFTER doc_structure or doc_search to identify relevant sections. "
        "Accepts comma-separated node_ids. Returns each section's title, "
        "full hierarchical path, page range, and complete text. "
        "IMPORTANT: Always cite which sections you used when answering."
    )

    async def execute(self, doc_id: str, node_id: str, **kwargs: Any) -> str:
        try:
            store = _get_store()
            node_ids = [n.strip() for n in node_id.split(",") if n.strip()]
            if not node_ids:
                return json.dumps({"error": "No valid node_ids provided."})
            chunks = store.get_chunks_by_node_ids(doc_id, node_ids)
            if not chunks:
                return json.dumps({
                    "error": f"Section(s) not found: {node_ids}",
                    "hint": "Use doc_structure to verify node_ids exist."
                }, ensure_ascii=False)
            results = [{
                "title": c.get("title"),
                "node_id": c.get("node_id"),
                "full_path": c.get("full_path"),
                "pages": f"{c.get('start_index')}-{c.get('end_index')}",
                "text": c.get("text", "(text not available — re-index with if_add_node_text=yes)"),
            } for c in chunks]
            total_chars = sum(len(r["text"]) for r in results)
            header = f"[{len(results)} section(s), {total_chars} chars]"
            return f"{header}\n\n{json.dumps(results, ensure_ascii=False, indent=2)}"
        except Exception as e:
            return json.dumps({"error": f"Failed to retrieve chunks: {e}"})
