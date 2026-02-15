"""Embedding service — generates vector embeddings from text.

Supports two providers:
  • stub  — deterministic hash-based embeddings for local dev / tests
  • openai — real embeddings via OpenAI API
"""

from __future__ import annotations

import hashlib
import logging
from typing import Protocol

import numpy as np

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


# ── Stub provider (deterministic, no external calls) ──────


class StubEmbeddingProvider:
    """Generates deterministic pseudo-embeddings by hashing text.
    Useful for end-to-end testing without an API key."""

    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            rng = np.random.RandomState(int.from_bytes(digest[:4], "big"))
            vec = rng.randn(self.dimension).astype(float)
            # L2-normalise for cosine similarity
            vec = vec / np.linalg.norm(vec)
            results.append(vec.tolist())
        return results


# ── OpenAI provider ───────────────────────────────────────


class OpenAIEmbeddingProvider:
    """Uses OpenAI embeddings API."""

    def __init__(self):
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.embedding_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.embeddings.create(
            input=texts,
            model=self.model,
        )
        return [item.embedding for item in response.data]


# ── Factory ───────────────────────────────────────────────


def get_embedding_provider() -> EmbeddingProvider:
    if settings.embedding_provider == "openai":
        return OpenAIEmbeddingProvider()
    return StubEmbeddingProvider(dimension=settings.embedding_dimension)
