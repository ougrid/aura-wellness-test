"""FastAPI dependency — extracts and validates tenant from request header."""

from __future__ import annotations

import uuid
from fastapi import Header, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.services.document_service import validate_tenant


async def get_tenant_id(
    x_tenant_id: str = Header(
        ...,
        description="UUID of the tenant making the request. "
        "Required for multi-tenant isolation.",
        examples=["a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"],
    ),
    db: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """Parse and validate the X-Tenant-Id header."""
    try:
        tid = uuid.UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Invalid X-Tenant-Id format (must be UUID)"
        )

    tenant = await validate_tenant(db, tid)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found or inactive")

    return tid
