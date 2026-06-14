"""
Nanobot tools for document RAG: doc_list, doc_structure, doc_search, doc_chunk.
Integrates with ChunkStore for leaf-level chunk retrieval.
"""

from __future__ import annotations

import json
from typing import Any

from nanobot.agent.tools.base import Tool, tool_parameters
from .chunk_store import ChunkStore

# Singleton store — initialize once at startup
_store: ChunkStore | None = None


def init_store(workspace_dir: str = "./doc_workspace") -> ChunkStore:
    global _store
    if _store is None:
        _store = ChunkStore(workspace_dir)
        _store.load_workspace()
    return _store


def get_store() -> ChunkStore:
    if _store is None:
        return init_store()
    return _store


# ── Tool: doc_list ────────────────────────────────────────────────────────

@tool_parameters({
    "type": "object",
    "properties": {},
    "required": [],
})
class DocListTool(Tool):
    """List all indexed documents with their IDs, names, and descriptions."""

    name = "doc_list"
    description = (
        "List all available documents that have been indexed and are ready for "
        "question answering. Returns each document's id, name, and a short description."
    )

    async def execute(self, **kwargs: Any) -> str:
        store = get_store()
        docs = store.list_documents()
        if not docs:
            return "No documents indexed yet. Please index documents first."
        return json.dumps(docs, ensure_ascii=False, indent=2)


# ── Tool: doc_structure ───────────────────────────────────────────────────

@tool_parameters({
    "type": "object",
    "properties": {
        "doc_id": {
            "type": "string",
            "description": "The document ID to retrieve the structure for."
        }
    },
    "required": ["doc_id"],
})
class DocStructureTool(Tool):
    """Get the full hierarchical table of contents tree for a document."""

    name = "doc_structure"
    description = (
        "Get the complete tree structure (table of contents) of a specific document. "
        "Returns each section's title, node_id, page range (start_index, end_index), "
        "and summary. Use this to find which sections are relevant to a user's question. "
        "Nodes with children are marked by a 'nodes' field; leaf nodes (most granular sections) "
        "have no 'nodes' field. Each node_id can be used with doc_chunk to get the full text."
    )

    async def execute(self, doc_id: str, **kwargs: Any) -> str:
        store = get_store()
        structure = store.get_document_structure(doc_id)
        if structure is None:
            return json.dumps({"error": f"Document {doc_id} not found"})
        return json.dumps(structure, ensure_ascii=False, indent=2)


# ── Tool: doc_search ─────────────────────────────────────────────────────

@tool_parameters({
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Keywords or short query to search for relevant chunks."
        },
        "doc_id": {
            "type": "string",
            "description": "Optional. Limit search to a specific document by its ID."
        },
        "top_k": {
            "type": "integer",
            "description": "Number of top results to return. Default 5, max 10."
        },
    },
    "required": ["query"],
})
class DocSearchTool(Tool):
    """Search for relevant document chunks by keyword / semantic query."""

    name = "doc_search"
    description = (
        "Search for the most relevant document sections (chunks) matching a query. "
        "Returns the top-matching leaf-level sections with their full hierarchical path, "
        "summary, and node_id. Use this to identify which specific sections to retrieve "
        "with doc_chunk. Each result shows: title, full_path, node_id, summary, page range."
    )

    async def execute(self, query: str, doc_id: str = "", top_k: int = 5, **kwargs: Any) -> str:
        store = get_store()
        did = doc_id if doc_id else None
        results = store.search(query, top_k=min(top_k, 10), doc_id=did)
        if not results:
            return json.dumps({
                "message": "No matching chunks found.",
                "hint": "Try different keywords or use doc_structure to browse the table of contents."
            }, ensure_ascii=False)
        previews = []
        for c in results:
            previews.append({
                "title": c.get("title", ""),
                "node_id": c.get("node_id", ""),
                "full_path": c.get("full_path", ""),
                "summary": c.get("summary", "")[:300],
                "start_index": c.get("start_index"),
                "end_index": c.get("end_index"),
            })
        return json.dumps(previews, ensure_ascii=False, indent=2)


# ── Tool: doc_chunk ───────────────────────────────────────────────────────

@tool_parameters({
    "type": "object",
    "properties": {
        "doc_id": {
            "type": "string",
            "description": "The document ID."
        },
        "node_id": {
            "type": "string",
            "description": (
                "The section node_id to retrieve full text for. Can also be a "
                "comma-separated list like '0003,0005,0008' for batch retrieval."
            )
        },
    },
    "required": ["doc_id", "node_id"],
})
class DocChunkTool(Tool):
    """Retrieve the full text content of specific document sections by their node_id."""

    name = "doc_chunk"
    description = (
        "Get the full text content of one or more document sections identified by their "
        "node_id. Use this AFTER browsing doc_structure or doc_search to identify "
        "relevant sections. Accepts a single node_id or a comma-separated list for "
        "batch retrieval (e.g., '0003,0005,0008'). Returns each chunk's full text "
        "along with its title, hierarchical path, and page range. "
        "IMPORTANT: always reference which sections you used when answering."
    )

    async def execute(self, doc_id: str, node_id: str, **kwargs: Any) -> str:
        store = get_store()
        node_ids = [nid.strip() for nid in node_id.split(",") if nid.strip()]
        chunks = store.get_chunks_by_node_ids(doc_id, node_ids)
        if not chunks:
            return json.dumps({
                "error": f"No chunks found for node_ids={node_ids} in document {doc_id}.",
                "hint": "Use doc_structure to verify the node_ids exist."
            }, ensure_ascii=False)
        results = []
        for c in chunks:
            text = c.get("text", "")
            results.append({
                "title": c.get("title", ""),
                "node_id": c.get("node_id", ""),
                "full_path": c.get("full_path", ""),
                "pages": f"{c.get('start_index')}-{c.get('end_index')}",
                "text": text,
            })
        total_chars = sum(len(r["text"]) for r in results)
        summary = json.dumps(results, ensure_ascii=False, indent=2)
        return f"[Total chunks: {len(results)}, total chars: {total_chars}]\n\n{summary}"


# ── Factory ───────────────────────────────────────────────────────────────

def create_doc_tools(workspace_dir: str = "./doc_workspace") -> list[Tool]:
    """Initialize the chunk store and return all document RAG tools."""
    init_store(workspace_dir)
    return [DocListTool(), DocStructureTool(), DocSearchTool(), DocChunkTool()]
