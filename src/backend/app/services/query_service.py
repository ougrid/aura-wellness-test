"""Query service — the RAG pipeline.

Flow:
  1. Check Redis cache for identical question (tenant-scoped)
  2. Embed the question
  3. Retrieve top-K chunks from pgvector (filtered by tenant_id)
  4. Send context + question to LLM
  5. Log the result to ai_requests (audit trail)
  6. Cache the result in Redis
  7. Return structured response
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import AIRequest
from app.services.cache_service import cache_service
from app.services.embedding_service import get_embedding_provider
from app.services.llm_service import get_llm_provider

logger = logging.getLogger(__name__)

TOP_K = 5  # number of chunks to retrieve
SIMILARITY_THRESHOLD = 0.3  # minimum cosine similarity to include


async def ask_question(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    question: str,
) -> dict:
    """End-to-end RAG query pipeline."""
    start_time = time.time()

    # ── 1. Cache check ────────────────────────────────────
    cached = await cache_service.get_cached_answer(str(tenant_id), question)
    if cached:
        # Log the cached hit in audit table
        ai_req = AIRequest(
            tenant_id=tenant_id,
            question=question,
            answer=cached.get("answer", ""),
            sources=cached.get("sources", []),
            status=cached.get("status", "completed"),
            cached=True,
            model_used=cached.get("model_used"),
            latency_ms=int((time.time() - start_time) * 1000),
        )
        db.add(ai_req)
        await db.flush()

        cached["request_id"] = str(ai_req.id)
        cached["cached"] = True
        cached["latency_ms"] = int((time.time() - start_time) * 1000)
        return cached

    # ── 2. Embed the question ─────────────────────────────
    embedder = get_embedding_provider()
    question_embeddings = await embedder.embed([question])
    q_vec = question_embeddings[0]

    # ── 3. Vector search (tenant-scoped) ──────────────────
    vec_str = "[" + ",".join(str(v) for v in q_vec) + "]"

    search_query = text(
        """
        SELECT
            dc.id AS chunk_id,
            dc.content,
            dc.metadata,
            dc.document_id,
            d.title AS document_title,
            1 - (dc.embedding <=> :query_vec::vector) AS similarity
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        WHERE dc.tenant_id = :tenant_id
          AND 1 - (dc.embedding <=> :query_vec::vector) > :threshold
        ORDER BY dc.embedding <=> :query_vec::vector
        LIMIT :top_k
    """
    )

    result = await db.execute(
        search_query,
        {
            "query_vec": vec_str,
            "tenant_id": str(tenant_id),
            "threshold": SIMILARITY_THRESHOLD,
            "top_k": TOP_K,
        },
    )
    rows = result.fetchall()

    context_chunks = [
        {
            "chunk_id": str(r.chunk_id),
            "content": r.content,
            "document_title": r.document_title,
            "similarity": float(r.similarity),
        }
        for r in rows
    ]

    logger.info(
        "Retrieved %d chunks for question (tenant=%s)",
        len(context_chunks),
        tenant_id,
    )

    # ── 4. LLM generation ────────────────────────────────
    llm = get_llm_provider()
    llm_result = await llm.generate(question, context_chunks)

    # ── 5. Build sources list ─────────────────────────────
    sources = [
        {
            "chunk_id": c["chunk_id"],
            "document_title": c["document_title"],
            "relevance_score": round(c["similarity"], 4),
            "excerpt": c["content"][:300],
        }
        for c in context_chunks
    ]

    status = "refused" if llm_result.refused else "completed"
    latency_ms = int((time.time() - start_time) * 1000)

    # ── 6. Audit log ──────────────────────────────────────
    ai_req = AIRequest(
        tenant_id=tenant_id,
        question=question,
        answer=llm_result.answer if not llm_result.refused else None,
        sources=sources,
        status=status,
        refused_reason=llm_result.refused_reason,
        prompt_tokens=llm_result.prompt_tokens,
        completion_tokens=llm_result.completion_tokens,
        total_tokens=llm_result.total_tokens,
        model_used=llm_result.model,
        latency_ms=latency_ms,
        cached=False,
    )
    db.add(ai_req)
    await db.flush()

    response_data = {
        "request_id": str(ai_req.id),
        "question": question,
        "answer": llm_result.answer or "",
        "sources": sources,
        "status": status,
        "refused_reason": llm_result.refused_reason,
        "cached": False,
        "model_used": llm_result.model,
        "latency_ms": latency_ms,
        "token_usage": {
            "prompt_tokens": llm_result.prompt_tokens,
            "completion_tokens": llm_result.completion_tokens,
            "total_tokens": llm_result.total_tokens,
        },
    }

    # ── 7. Cache (only successful answers) ────────────────
    if status == "completed":
        await cache_service.set_cached_answer(str(tenant_id), question, response_data)

    return response_data
