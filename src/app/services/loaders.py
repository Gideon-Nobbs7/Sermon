"""Load and chunk `.docx` / `.pdf` files into `Chunk`s."""

from __future__ import annotations

import os
from typing import List

from langchain_community.document_loaders import (
    Docx2txtLoader,
    PyPDFLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ..schemas.sermon import Chunk, SourceType

_CHUNK_SIZE = 1000
_CHUNK_OVERLAP = 100


def load_document(filepath: str) -> List[Chunk]:
    """Load a `.pdf` or `.docx` file and return its chunks."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        loader = PyPDFLoader(filepath)
    elif ext in (".docx", ".doc"):
        loader = Docx2txtLoader(filepath)
    else:
        raise ValueError(f"unsupported document type: {ext}")

    source = os.path.basename(filepath)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=_CHUNK_SIZE,
        chunk_overlap=_CHUNK_OVERLAP,
    )

    chunks: List[Chunk] = []
    for doc in loader.load():
        page = doc.metadata.get("page", 0)
        for i, text in enumerate(splitter.split_text(doc.page_content)):
            chunks.append(Chunk(
                id=f"document_{os.path.splitext(source)[0]}_{page}_{i}",
                source_file=source,
                source_type=SourceType.DOCUMENT,
                page=page,
                text=text.strip(),
            ))
    return chunks
