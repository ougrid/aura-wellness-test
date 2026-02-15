"""API routes for the Internal Knowledge Assistant."""

from __future__ import annotations

import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_tenant_id
from app.api.dto import (
    DocumentCreate,
    DocumentOut,
    QueryRequest,
    QueryResponse,
    FeedbackCreate,
    FeedbackOut,
    TenantOut,
    SourceReference,
)
from app.models.database import get_db
from app.models.schemas import Tenant, AIRequest, Feedback
from app.services import document_service, query_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Tenants ──────────────────────────────────────────────


@router.get("/tenants", response_model=list[TenantOut], tags=["tenants"])
async def list_tenants(db: AsyncSession = Depends(get_db)):
    """List all active tenants."""
    result = await db.execute(
        select(Tenant).where(Tenant.is_active == True).order_by(Tenant.name)
    )
    return result.scalars().all()


# ── Documents ────────────────────────────────────────────


@router.post("/documents", tags=["documents"], status_code=201)
async def ingest_document(
    body: DocumentCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Ingest a document: store → chunk → embed → index for RAG retrieval."""
    result = await document_service.ingest_document(
        db=db,
        tenant_id=tenant_id,
        title=body.title,
        content=body.content,
        doc_type=body.doc_type,
        metadata=body.metadata,
    )
    return result


@router.get("/documents", tags=["documents"])
async def list_documents(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """List all documents for the authenticated tenant."""
    return await document_service.list_documents(db, tenant_id)


@router.delete("/documents/{document_id}", tags=["documents"], status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete a document (tenant-scoped, cascades to chunks)."""
    deleted = await document_service.delete_document(db, tenant_id, document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")


# ── Query (Ask) ──────────────────────────────────────────


@router.post("/ask", response_model=QueryResponse, tags=["query"])
async def ask_question(
    body: QueryRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Ask a question — RAG pipeline: embed → retrieve → generate → cache."""
    result = await query_service.ask_question(
        db=db,
        tenant_id=tenant_id,
        question=body.question,
    )

    # Map raw dicts to SourceReference models
    sources = [
        SourceReference(
            chunk_id=s["chunk_id"],
            document_title=s["document_title"],
            relevance_score=s["relevance_score"],
            excerpt=s["excerpt"],
        )
        for s in result.get("sources", [])
    ]

    return QueryResponse(
        request_id=result["request_id"],
        question=result["question"],
        answer=result["answer"],
        sources=sources,
        status=result["status"],
        refused_reason=result.get("refused_reason"),
        cached=result.get("cached", False),
        model_used=result.get("model_used"),
        latency_ms=result.get("latency_ms"),
        token_usage=result.get("token_usage", {}),
    )


# ── Feedback ─────────────────────────────────────────────


@router.post(
    "/requests/{request_id}/feedback",
    response_model=FeedbackOut,
    tags=["feedback"],
    status_code=201,
)
async def submit_feedback(
    request_id: uuid.UUID,
    body: FeedbackCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Submit human feedback on an AI response (1-5 rating + optional comment)."""
    # Verify the request belongs to this tenant
    ai_request = await db.execute(
        select(AIRequest).where(
            AIRequest.id == request_id,
            AIRequest.tenant_id == tenant_id,
        )
    )
    if not ai_request.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="AI request not found")

    fb = Feedback(
        request_id=request_id,
        tenant_id=tenant_id,
        rating=body.rating,
        comment=body.comment,
    )
    db.add(fb)
    await db.flush()
    return fb


# ── Request History ──────────────────────────────────────


@router.get("/requests", tags=["audit"])
async def list_requests(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
):
    """List AI request history for audit/review (tenant-scoped)."""
    result = await db.execute(
        select(AIRequest)
        .where(AIRequest.tenant_id == tenant_id)
        .order_by(AIRequest.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "question": r.question,
            "status": r.status,
            "cached": r.cached,
            "model_used": r.model_used,
            "total_tokens": r.total_tokens,
            "latency_ms": r.latency_ms,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
