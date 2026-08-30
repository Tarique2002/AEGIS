"""Data access layer and repository for Evaluation and Reflection records."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.evaluation import EvaluationModel, ReflectionModel
from app.evaluation.schemas import EvaluationResult, ReflectionRecord


class EvaluationRepository:
    """Async repository for persisting and querying Evaluation and Reflection records."""

    async def create_evaluation(
        self,
        evaluation: EvaluationResult,
        session: AsyncSession,
    ) -> EvaluationModel:
        """Persist an evaluation result record to PostgreSQL."""
        model = EvaluationModel(
            id=evaluation.evaluation_id,
            task_id=evaluation.task_id,
            run_id=evaluation.run_id,
            overall_score=evaluation.overall_score,
            passed=evaluation.passed,
            evaluator=evaluation.evaluator,
            criterion_scores=[cs.model_dump(mode="json") for cs in evaluation.criterion_scores],
            failure_categories=[fc.value for fc in evaluation.failure_categories],
            strengths=evaluation.strengths,
            weaknesses=evaluation.weaknesses,
            recommendations=evaluation.recommendations,
            evaluation_metadata=evaluation.metadata,
        )
        session.add(model)
        await session.flush()
        return model

    async def get_evaluation_by_id(
        self,
        evaluation_id: uuid.UUID,
        session: AsyncSession,
    ) -> EvaluationModel | None:
        """Fetch an evaluation record by its primary key UUID."""
        stmt = select(EvaluationModel).where(EvaluationModel.id == evaluation_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_evaluations_by_task_id(
        self,
        task_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[EvaluationModel]:
        """Fetch all evaluation records for a specific task."""
        stmt = (
            select(EvaluationModel)
            .where(EvaluationModel.task_id == task_id)
            .order_by(EvaluationModel.created_at.desc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_evaluations_by_run_id(
        self,
        run_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[EvaluationModel]:
        """Fetch all evaluation records for a specific run."""
        stmt = (
            select(EvaluationModel)
            .where(EvaluationModel.run_id == run_id)
            .order_by(EvaluationModel.created_at.desc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def create_reflection(
        self,
        reflection: ReflectionRecord,
        session: AsyncSession,
    ) -> ReflectionModel:
        """Persist a reflection record to PostgreSQL."""
        model = ReflectionModel(
            id=reflection.reflection_id,
            evaluation_id=reflection.evaluation_id,
            task_id=reflection.task_id,
            run_id=reflection.run_id,
            summary=reflection.summary,
            what_went_well=reflection.what_went_well,
            what_went_wrong=reflection.what_went_wrong,
            root_causes=reflection.root_causes,
            improvement_suggestions=reflection.improvement_suggestions,
            confidence=reflection.confidence,
            reflection_metadata=reflection.metadata,
        )
        session.add(model)
        await session.flush()
        return model

    async def get_reflection_by_id(
        self,
        reflection_id: uuid.UUID,
        session: AsyncSession,
    ) -> ReflectionModel | None:
        """Fetch a reflection record by its primary key UUID."""
        stmt = select(ReflectionModel).where(ReflectionModel.id == reflection_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_reflection_by_evaluation_id(
        self,
        evaluation_id: uuid.UUID,
        session: AsyncSession,
    ) -> ReflectionModel | None:
        """Fetch a reflection record associated with an evaluation."""
        stmt = select(ReflectionModel).where(ReflectionModel.evaluation_id == evaluation_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
