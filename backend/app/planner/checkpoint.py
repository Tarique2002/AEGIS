"""Execution checkpoint manager for capturing state snapshots and enabling resume."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.plan import ExecutionCheckpointModel
from app.planner.schemas import ExecutionCheckpoint, ExecutionContext, NodeStatus
from app.schemas.common import utc_now


class CheckpointManager:
    """
    Manages durable state snapshots during execution graph runs.
    Ensures safe, recoverable resumption without re-executing already completed nodes.
    """

    @staticmethod
    def _sanitize_data(data: dict[str, Any]) -> dict[str, Any]:
        """Strip sensitive credentials before persisting checkpoint."""
        sanitized: dict[str, Any] = {}
        sensitive_keys = {
            "api_key",
            "secret",
            "password",
            "authorization",
            "bearer",
            "token",
        }
        for k, v in data.items():
            if any(s in str(k).lower() for s in sensitive_keys):
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, dict):
                sanitized[k] = CheckpointManager._sanitize_data(v)
            else:
                sanitized[k] = v
        return sanitized

    async def save_checkpoint(
        self,
        context: ExecutionContext,
        completed_nodes: list[str],
        node_states: dict[str, NodeStatus],
        node_outputs: dict[str, Any],
        session: AsyncSession,
    ) -> ExecutionCheckpoint:
        """Persist a new execution checkpoint."""
        checkpoint_id = uuid.uuid4()
        now = utc_now()
        clean_outputs = self._sanitize_data(node_outputs)
        raw_states = {k: v.value for k, v in node_states.items()}

        model = ExecutionCheckpointModel(
            id=checkpoint_id,
            plan_id=context.plan_id,
            task_id=context.task_id,
            run_id=context.run_id,
            completed_nodes=completed_nodes,
            node_states=raw_states,
            node_outputs=clean_outputs,
            checkpoint_metadata={"completed_count": len(completed_nodes)},
            created_at=now,
            updated_at=now,
        )
        session.add(model)
        await session.flush()

        return ExecutionCheckpoint(
            checkpoint_id=checkpoint_id,
            plan_id=context.plan_id,
            task_id=context.task_id,
            run_id=context.run_id,
            completed_nodes=completed_nodes,
            node_states=node_states,
            node_outputs=clean_outputs,
            created_at=now,
        )

    async def get_latest_checkpoint(
        self,
        plan_id: uuid.UUID,
        session: AsyncSession,
    ) -> ExecutionCheckpoint | None:
        """Fetch the most recent checkpoint for a given plan."""
        stmt = (
            select(ExecutionCheckpointModel)
            .where(ExecutionCheckpointModel.plan_id == plan_id)
            .order_by(ExecutionCheckpointModel.created_at.desc())
        )
        res = await session.execute(stmt)
        models = list(res.scalars().all())
        if not models:
            return None

        # If timestamps match, pick the model with the largest number of completed nodes
        model = max(
            models,
            key=lambda m: (
                m.created_at,
                len(m.completed_nodes) if isinstance(m.completed_nodes, list) else 0,
            ),
        )

        states: dict[str, NodeStatus] = {k: NodeStatus(v) for k, v in model.node_states.items()}
        return ExecutionCheckpoint(
            checkpoint_id=model.id,
            plan_id=model.plan_id,
            task_id=model.task_id,
            run_id=model.run_id,
            completed_nodes=model.completed_nodes,
            node_states=states,
            node_outputs=model.node_outputs,
            created_at=model.created_at,
            metadata=model.checkpoint_metadata,
        )
