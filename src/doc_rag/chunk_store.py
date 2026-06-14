"""
Document chunk store: loads PageIndex JSON output, extracts leaf-node chunks,
and provides keyword search + exact retrieval.
"""

import json
import os
import re
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


def _get_leaf_nodes(node: dict) -> list[dict]:
    """Extract all leaf nodes from a tree node (recursively)."""
    if "nodes" not in node or not node["nodes"]:
        return [{k: v for k, v in node.items() if k != "nodes"}]
    leaves = []
    for child in node["nodes"]:
        leaves.extend(_get_leaf_nodes(child))
    return leaves


def _get_node_path(structure: list[dict], target_node_id: str) -> list[str] | None:
    """Find the hierarchical path (titles from root to target node_id)."""
    def _search(nodes: list[dict], path: list[str]) -> list[str] | None:
        for node in nodes:
            current = [*path, node.get("title", "")]
            if node.get("node_id") == target_node_id:
                return current
            if "nodes" in node:
                result = _search(node["nodes"], current)
                if result:
                    return result
        return None
    return _search(structure, [])


class ChunkStore:
    """Manages document chunks extracted from PageIndex JSON output."""

    def __init__(self, workspace_dir: str = "./doc_workspace"):
        self.workspace = Path(workspace_dir)
        self.documents: dict[str, dict] = {}       # doc_id -> meta
        self.chunks: list[dict] = []               # flat chunk list
        self.inverted_index: dict[str, set[int]] = defaultdict(set)  # token -> set(chunk_indices)
        self.doc_freq: dict[str, int] = {}         # token -> document frequency
        self._loaded = False

    def index_document(self, pageindex_json_path: str) -> str:
        """Load a PageIndex output JSON and extract leaf chunks."""
        with open(pageindex_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        doc_id = data.get("id") or Path(pageindex_json_path).stem
        doc_name = data.get("doc_name", "")
        doc_description = data.get("doc_description", "")
        structure = data.get("structure", [])

        self.documents[doc_id] = {
            "id": doc_id,
            "doc_name": doc_name,
            "doc_description": doc_description,
            "structure": structure,
            "source_path": pageindex_json_path,
        }

        leaves = []
        for root_node in structure:
            leaves.extend(_get_leaf_nodes(root_node))

        for leaf in leaves:
            path_titles = _get_node_path(structure, leaf.get("node_id", "")) or [leaf.get("title", "")]
            leaf["full_path"] = " > ".join(p for p in path_titles if p)
            leaf["doc_id"] = doc_id
            leaf["doc_name"] = doc_name

        self.chunks.extend(leaves)
        self._index_chunks(leaves, doc_id)
        self._loaded = True
        return doc_id

    def load_workspace(self):
        """Load all JSON files from the workspace directory."""
        if not self.workspace.exists():
            return
        meta_path = self.workspace / "_meta.json"
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            for doc_id in meta:
                doc_path = self.workspace / f"{doc_id}.json"
                if doc_path.exists():
                    self.index_document(str(doc_path))
        else:
            for json_file in self.workspace.glob("*.json"):
                if json_file.name == "_meta.json":
                    continue
                self.index_document(str(json_file))

    # ── tokenization ──────────────────────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple CJK-aware tokenizer. Splits on non-alphanumeric, keeps CJK chars as unigrams."""
        tokens = []
        for char in text:
            if char.isalpha() or char.isdigit():
                tokens.append(char.lower())
            elif '一' <= char <= '鿿' or '㐀' <= char <= '䶿':
                tokens.append(char)
            else:
                tokens.append(" ")
        merged = "".join(tokens)
        return [t for t in merged.split() if len(t) > 1 or '一' <= t <= '鿿']

    def _index_chunks(self, chunks: list[dict], doc_id: str):
        """Build inverted index for a set of chunks."""
        base_idx = len(self.chunks) - len(chunks)
        for i, chunk in enumerate(chunks):
            idx = base_idx + i
            text = f"{chunk.get('full_path', '')} {chunk.get('title', '')} {chunk.get('summary', '')} {chunk.get('text', '')}"
            tokens = set(self._tokenize(text))
            for token in tokens:
                self.inverted_index[token].add(idx)
                self.doc_freq[token] = self.doc_freq.get(token, 0) + 1

    # ── retrieval ─────────────────────────────────────────────────────────

    _K1 = 1.2
    _B = 0.75

    @staticmethod
    def _chunk_search_text(chunk: dict) -> str:
        """Build searchable text from all available fields."""
        return " ".join(filter(None, [
            chunk.get("full_path", ""),
            chunk.get("title", ""),
            chunk.get("summary", ""),
            chunk.get("text", ""),
        ]))

    def search(self, query: str, top_k: int = 5, doc_id: str | None = None) -> list[dict]:
        """BM25 search across title, summary, full_path, and text. Returns top-k chunks."""
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        total_docs = len(self.chunks) or 1
        avg_len = sum(len(self._chunk_search_text(c)) for c in self.chunks) / total_docs
        if avg_len == 0:
            return []

        scores: dict[int, float] = defaultdict(float)
        for token in query_tokens:
            matching = self.inverted_index.get(token, set())
            if doc_id:
                matching = {i for i in matching if self.chunks[i].get("doc_id") == doc_id}
            df = len(matching)
            if df == 0:
                continue
            idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1.0)
            for idx in matching:
                chunk = self.chunks[idx]
                text = self._chunk_search_text(chunk)
                if not text:
                    continue
                tf = text.lower().count(token) / len(text)
                doc_len = len(text)
                norm = 1 - self._B + self._B * (doc_len / avg_len)
                scores[idx] += idf * (tf * (self._K1 + 1)) / (tf + self._K1 * norm)

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [self.chunks[idx] for idx, _score in ranked]

    def get_chunk(self, doc_id: str, node_id: str) -> dict | None:
        """Retrieve a chunk by doc_id and node_id (leaf or non-leaf)."""
        for chunk in self.chunks:
            if chunk.get("doc_id") == doc_id and chunk.get("node_id") == node_id:
                return chunk
        # Also search non-leaf nodes in structure
        doc = self.documents.get(doc_id)
        if not doc:
            return None
        structure = doc.get("structure", [])
        node = self._find_node_in_structure(structure, node_id)
        if node:
            path_titles = _get_node_path(structure, node_id) or [node.get("title", "")]
            node = dict(node)
            node["full_path"] = " > ".join(p for p in path_titles if p)
            node["doc_id"] = doc_id
            node["doc_name"] = doc.get("doc_name", "")
            return node
        return None

    def get_chunks_by_node_ids(self, doc_id: str, node_ids: list[str]) -> list[dict]:
        """Retrieve multiple chunks by their node_ids (leaf and non-leaf)."""
        result = []
        for nid in node_ids:
            chunk = self.get_chunk(doc_id, nid)
            if chunk:
                result.append(chunk)
        return result

    @staticmethod
    def _find_node_in_structure(nodes: list[dict], target_id: str) -> dict | None:
        """Find any node (leaf or branch) in a structure tree by node_id."""
        for node in nodes:
            if node.get("node_id") == target_id:
                return node
            if "nodes" in node:
                found = ChunkStore._find_node_in_structure(node["nodes"], target_id)
                if found:
                    return found
        return None

    def list_documents(self) -> list[dict]:
        """Return metadata for all indexed documents."""
        return [
            {"doc_id": did, "doc_name": d["doc_name"], "doc_description": d["doc_description"]}
            for did, d in self.documents.items()
        ]

    def get_document_structure(self, doc_id: str) -> list[dict] | None:
        """Return the tree structure (without text) for a document."""
        doc = self.documents.get(doc_id)
        if not doc:
            return None

        def _strip_text(nodes: list[dict]) -> list[dict]:
            result = []
            for node in nodes:
                clean = {
                    "title": node.get("title", ""),
                    "node_id": node.get("node_id", ""),
                    "start_index": node.get("start_index"),
                    "end_index": node.get("end_index"),
                    "summary": node.get("summary", ""),
                }
                if "nodes" in node and node["nodes"]:
                    clean["nodes"] = _strip_text(node["nodes"])
                result.append(clean)
            return result

        return _strip_text(doc["structure"])

    def get_chunk_count(self) -> int:
        return len(self.chunks)

    def stats(self) -> dict:
        return {
            "documents": len(self.documents),
            "chunks": len(self.chunks),
            "vocabulary": len(self.inverted_index),
        }
