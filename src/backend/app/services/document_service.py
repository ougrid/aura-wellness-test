"""Document service — ingestion, chunking, and embedding pipeline.

Chunking strategy:
  • Split by paragraphs (double newline) first
  • Merge small paragraphs until reaching ~500 tokens per chunk
  • Overlap: last sentence of previous chunk prepended to next chunk
  • This balances retrieval precision vs. context completeness
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Optional

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import Document, DocumentChunk, Tenant
from app.services.embedding_service import get_embedding_provider
from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)

# ── Chunking parameters ──────────────────────────────────

MAX_CHUNK_TOKENS = 500
OVERLAP_SENTENCES = 1


def _estimate_tokens(text: str) -> int:
    """Rough token estimation (~0.75 words per token for English)."""
    return max(1, int(len(text.split()) / 0.75))


def chunk_text(text: str, max_tokens: int = MAX_CHUNK_TOKENS) -> list[str]:
    """Split text into chunks respecting paragraph boundaries.

    Strategy:
      1. Split on double-newlines (paragraphs)
      2. Accumulate paragraphs until max_tokens is reached
      3. Add 1-sentence overlap between chunks for continuity
    """
    paragraphs = re.split(r"\n{2,}", text.strip())
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = _estimate_tokens(para)

        if current_tokens + para_tokens > max_tokens and current:
            chunk_text_val = "\n\n".join(current)
            chunks.append(chunk_text_val)

            # Overlap: carry last sentence forward
            last_sentences = re.split(r"(?<=[.!?])\s+", current[-1])
            overlap = last_sentences[-1] if last_sentences else ""
            current = [overlap, para] if overlap else [para]
            current_tokens = _estimate_tokens("\n\n".join(current))
        else:
            current.append(para)
            current_tokens += para_tokens

    if current:
        chunks.append("\n\n".join(current))

    return chunks


# ── Service functions ────────────────────────────────────


async def validate_tenant(db: AsyncSession, tenant_id: uuid.UUID) -> Optional[Tenant]:
    """Verify tenant exists and is active."""
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.is_active == True)
    )
    return result.scalar_one_or_none()


async def ingest_document(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    title: str,
    content: str,
    doc_type: str = "markdown",
    metadata: dict | None = None,
) -> dict:
    """Full ingestion pipeline: store document → chunk → embed → persist chunks."""
    # 1. Store the raw document
    doc = Document(
        tenant_id=tenant_id,
        title=title,
        content=content,
        doc_type=doc_type,
        metadata=metadata or {},
    )
    db.add(doc)
    await db.flush()  # get doc.id

    # 2. Chunk the content
    text_chunks = chunk_text(content)
    logger.info("Document '%s' split into %d chunks", title, len(text_chunks))

    # 3. Generate embeddings for all chunks in one batch
    embedder = get_embedding_provider()
    embeddings = await embedder.embed(text_chunks)

    # 4. Persist chunks with embeddings
    chunk_records = []
    for idx, (chunk_content, embedding) in enumerate(zip(text_chunks, embeddings)):
        chunk = DocumentChunk(
            document_id=doc.id,
            tenant_id=tenant_id,
            chunk_index=idx,
            content=chunk_content,
            token_count=_estimate_tokens(chunk_content),
            embedding=embedding,
            metadata={"document_title": title},
        )
        db.add(chunk)
        chunk_records.append(chunk)

    await db.flush()

    # 5. Invalidate cached queries for this tenant (new knowledge available)
    await cache_service.invalidate_tenant(str(tenant_id))

    return {
        "document_id": str(doc.id),
        "title": title,
        "chunk_count": len(chunk_records),
        "total_tokens": sum(c.token_count for c in chunk_records),
    }


async def list_documents(db: AsyncSession, tenant_id: uuid.UUID) -> list[dict]:
    """List all documents for a tenant with chunk counts."""
    result = await db.execute(
        select(
            Document.id,
            Document.title,
            Document.doc_type,
            Document.metadata,
            Document.created_at,
            func.count(DocumentChunk.id).label("chunk_count"),
        )
        .outerjoin(DocumentChunk, Document.id == DocumentChunk.document_id)
        .where(Document.tenant_id == tenant_id)
        .group_by(Document.id)
        .order_by(Document.created_at.desc())
    )
    rows = result.all()
    return [
        {
            "id": str(r.id),
            "title": r.title,
            "doc_type": r.doc_type,
            "metadata": r.metadata,
            "chunk_count": r.chunk_count,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


async def delete_document(
    db: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID
) -> bool:
    """Delete a document and its chunks (cascading)."""
    result = await db.execute(
        delete(Document).where(
            Document.id == document_id,
            Document.tenant_id == tenant_id,  # tenant isolation
        )
    )
    if result.rowcount > 0:
        await cache_service.invalidate_tenant(str(tenant_id))
        return True
    return False
