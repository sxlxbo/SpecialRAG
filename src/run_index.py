#!/usr/bin/env python3
"""
Index a PDF or Markdown document and save the chunk-ready workspace JSON.

Usage:
    python run_index.py --pdf /path/to/doc.pdf
    python run_index.py --md /path/to/doc.md
    python run_index.py --pdf /path/to/doc.pdf --workspace ./my_workspace
    python run_index.py --pdf /path/to/doc.pdf --model openai/gpt-4o-mini
"""

import argparse
import os
import sys
import json
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "PageIndex-main"))

from pageindex import PageIndexClient


def main():
    parser = argparse.ArgumentParser(
        description="Index a document with PageIndex and save workspace JSON"
    )
    parser.add_argument("--pdf", type=str, help="Path to PDF file")
    parser.add_argument("--md", type=str, help="Path to Markdown file")
    parser.add_argument("--workspace", type=str, default="./doc_workspace",
                        help="Output workspace directory (default: ./doc_workspace)")
    parser.add_argument("--model", type=str, default=None,
                        help="LLM model (e.g. openai/gpt-4o, anthropic/claude-sonnet-4-6)")
    parser.add_argument("--retrieve-model", type=str, default=None,
                        help="Model for retrieval/QA phase")
    parser.add_argument("--api-key", type=str, default=None,
                        help="API key (or set OPENAI_API_KEY env var)")
    args = parser.parse_args()

    if not args.pdf and not args.md:
        parser.error("Either --pdf or --md is required")

    file_path = args.pdf or args.md
    if not os.path.isfile(file_path):
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    print(f"Initializing PageIndex client...")
    client = PageIndexClient(
        api_key=args.api_key,
        model=args.model,
        retrieve_model=args.retrieve_model,
        workspace=args.workspace,
    )

    mode = "pdf" if args.pdf else "md"
    print(f"Indexing [{mode}]: {file_path}")
    doc_id = client.index(file_path)
    print(f"\nDone. Document ID: {doc_id}")
    print(f"Workspace: {os.path.abspath(args.workspace)}")
    print(f"Files created:")
    print(f"  {args.workspace}/_meta.json")
    print(f"  {args.workspace}/{doc_id}.json")


if __name__ == "__main__":
    main()
