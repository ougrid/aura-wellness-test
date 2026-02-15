"""Pydantic request / response models for the API layer."""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


# ── Tenant ──────────────────────────────────────────────────


class TenantOut(BaseModel):
    id: UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Documents ───────────────────────────────────────────────


class DocumentCreate(BaseModel):
    title: str = Field(..., max_length=500)
    content: str = Field(..., min_length=1)
    doc_type: str = Field(default="markdown", pattern="^(markdown|text|pdf)$")
    metadata: dict = Field(default_factory=dict)


class DocumentOut(BaseModel):
    id: UUID
    tenant_id: UUID
    title: str
    doc_type: str
    metadata: dict
    chunk_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Query (Ask) ─────────────────────────────────────────────


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)


class SourceReference(BaseModel):
    chunk_id: UUID
    document_title: str
    relevance_score: float
    excerpt: str


class QueryResponse(BaseModel):
    request_id: UUID
    question: str
    answer: str
    sources: list[SourceReference]
    status: str  # completed | refused
    refused_reason: Optional[str] = None
    cached: bool = False
    model_used: Optional[str] = None
    latency_ms: Optional[int] = None
    token_usage: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}


# ── Feedback ────────────────────────────────────────────────


class FeedbackCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None


class FeedbackOut(BaseModel):
    id: UUID
    request_id: UUID
    rating: int
    comment: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Health ──────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str
    postgres: str
    redis: str
    version: str = "1.0.0"
