"""Redis cache service — caches query results to reduce LLM costs."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

import redis.asyncio as redis

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class CacheService:
    """Thin wrapper around Redis for tenant-scoped query caching."""

    def __init__(self):
        self.redis: Optional[redis.Redis] = None

    async def connect(self):
        self.redis = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
        )
        logger.info("Redis connection established")

    async def disconnect(self):
        if self.redis:
            await self.redis.aclose()
            logger.info("Redis connection closed")

    async def ping(self) -> bool:
        try:
            if self.redis:
                return await self.redis.ping()
        except Exception:
            return False
        return False

    # ── Cache key construction ────────────────────────────

    @staticmethod
    def _cache_key(tenant_id: str, question: str) -> str:
        """Deterministic cache key scoped by tenant + normalised question."""
        normalised = question.strip().lower()
        q_hash = hashlib.sha256(normalised.encode()).hexdigest()[:16]
        return f"ka:query:{tenant_id}:{q_hash}"

    # ── Get / set ─────────────────────────────────────────

    async def get_cached_answer(self, tenant_id: str, question: str) -> Optional[dict]:
        """Return cached answer dict or None."""
        if not self.redis:
            return None
        try:
            key = self._cache_key(tenant_id, question)
            raw = await self.redis.get(key)
            if raw:
                logger.info("Cache HIT for key=%s", key)
                return json.loads(raw)
            logger.debug("Cache MISS for key=%s", key)
        except Exception as exc:
            logger.warning("Cache read error: %s", exc)
        return None

    async def set_cached_answer(
        self, tenant_id: str, question: str, answer_data: dict
    ) -> None:
        """Store answer in cache with TTL."""
        if not self.redis:
            return
        try:
            key = self._cache_key(tenant_id, question)
            await self.redis.setex(
                key,
                settings.cache_ttl_seconds,
                json.dumps(answer_data, default=str),
            )
            logger.info(
                "Cached answer for key=%s (TTL=%ds)", key, settings.cache_ttl_seconds
            )
        except Exception as exc:
            logger.warning("Cache write error: %s", exc)

    async def invalidate_tenant(self, tenant_id: str) -> int:
        """Remove all cached queries for a tenant (e.g. after document update)."""
        if not self.redis:
            return 0
        pattern = f"ka:query:{tenant_id}:*"
        count = 0
        async for key in self.redis.scan_iter(match=pattern, count=100):
            await self.redis.delete(key)
            count += 1
        logger.info("Invalidated %d cache entries for tenant=%s", count, tenant_id)
        return count


# ── Singleton ─────────────────────────────────────────────

cache_service = CacheService()
