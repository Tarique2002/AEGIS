"""Tool endpoints for discovery, inspection, and controlled development execution."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.tools.schemas import ToolDefinition, ToolInvocation, ToolObservation
from app.tools.service import ToolService

router = APIRouter(prefix="/tools", tags=["Tools"])


def get_tool_service() -> ToolService:
    """Dependency provider for ToolService."""
    return ToolService()


@router.get(
    "",
    response_model=list[ToolDefinition],
    status_code=status.HTTP_200_OK,
    summary="List available tools",
    description="Returns definitions and capability schemas for all enabled, registered tools.",
)
async def list_tools(
    service: ToolService = Depends(get_tool_service),
) -> list[ToolDefinition]:
    return service.list_tools()


@router.get(
    "/{name}",
    response_model=ToolDefinition,
    status_code=status.HTTP_200_OK,
    summary="Get tool definition",
    description="Retrieves the capability and input schema for a specific registered tool.",
)
async def get_tool(
    name: str,
    service: ToolService = Depends(get_tool_service),
) -> ToolDefinition:
    return service.get_tool_by_name(name)


@router.post(
    "/execute",
    response_model=ToolObservation,
    status_code=status.HTTP_200_OK,
    summary="Execute tool in controlled boundary",
    description=(
        "Development/testing endpoint executing a tool through the full validation, "
        "policy, timeout, and exception pipeline. Never calls tool implementations directly."
    ),
)
async def execute_tool(
    invocation: ToolInvocation,
    session: AsyncSession = Depends(get_db_session),
    service: ToolService = Depends(get_tool_service),
) -> ToolObservation:
    return await service.execute_tool(invocation, session=session)
