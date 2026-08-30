"""Memory API endpoints for controlled ingestion, multi-tier search, and lifecycle operations."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user_id
from app.db.session import get_db_session
from app.memory.schemas import (
    MemoryCandidate,
    MemoryRecord,
    MemorySearchQuery,
    MemorySearchResult,
    MemoryType,
)
from app.memory.service import MemoryService

router = APIRouter(prefix="/memory", tags=["Memory"])


def get_memory_service() -> MemoryService:
    """Dependency provider for MemoryService."""
    return MemoryService()


@router.post(
    "",
    response_model=MemoryRecord,
    status_code=status.HTTP_201_CREATED,
    summary="Store memory candidate",
    description="Ingests a memory item through validation, policy checks, and deduplication.",
)
async def store_memory(
    candidate: MemoryCandidate,
    trusted_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
    service: MemoryService = Depends(get_memory_service),
) -> MemoryRecord:
    return await service.remember(
        candidate=candidate,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.post(
    "/search",
    response_model=list[MemorySearchResult],
    status_code=status.HTTP_200_OK,
    summary="Search memory layers",
    description="Multi-tier semantic and keyword search ranked with multi-factor scoring.",
)
async def search_memory(
    query: MemorySearchQuery,
    trusted_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
    service: MemoryService = Depends(get_memory_service),
) -> list[MemorySearchResult]:
    # Ensure trusted user_id overrides any request body value
    query.user_id = trusted_user_id
    return await service.recall(
        query=query,
        trusted_user_id=trusted_user_id,
        session=session,
    )


@router.get(
    "/{memory_id}",
    response_model=MemoryRecord,
    status_code=status.HTTP_200_OK,
    summary="Get memory by ID",
    description="Retrieves a specific memory item with strict ownership verification.",
)
async def get_memory(
    memory_id: uuid.UUID,
    memory_type: MemoryType | None = None,
    trusted_user_id: uuid.UUID = Depends(get_current_user_id),
    service: MemoryService = Depends(get_memory_service),
) -> MemoryRecord:
    return await service.get_memory(
        memory_id=memory_id,
        trusted_user_id=trusted_user_id,
        memory_type=memory_type,
    )


@router.delete(
    "/{memory_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete memory item",
    description="Deletes a memory item with strict ownership verification.",
)
async def delete_memory(
    memory_id: uuid.UUID,
    memory_type: MemoryType | None = None,
    trusted_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
    service: MemoryService = Depends(get_memory_service),
) -> dict[str, bool]:
    success = await service.forget_memory(
        memory_id=memory_id,
        trusted_user_id=trusted_user_id,
        memory_type=memory_type,
        session=session,
    )
    return {"deleted": success}
