"""State lifecycle rules and validation for tasks and agent runs."""

from app.core.errors import InvalidStateTransitionError
from app.schemas.common import TaskStatus

# Define valid state transitions for TaskStatus
VALID_TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {
        TaskStatus.RUNNING,
        TaskStatus.PLANNING,
        TaskStatus.EXECUTING,
        TaskStatus.CANCELLED,
    },
    TaskStatus.RUNNING: {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.WAITING_APPROVAL,
        TaskStatus.PLANNING,
        TaskStatus.EXECUTING,
    },
    TaskStatus.PLANNING: {
        TaskStatus.RUNNING,
        TaskStatus.EXECUTING,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.EXECUTING: {
        TaskStatus.RUNNING,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.WAITING_APPROVAL,
    },
    TaskStatus.WAITING_APPROVAL: {
        TaskStatus.RUNNING,
        TaskStatus.EXECUTING,
        TaskStatus.CANCELLED,
    },
    # Terminal states have no outbound transitions
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}


def validate_task_transition(from_status: TaskStatus, to_status: TaskStatus) -> bool:
    """
    Validate whether a transition from one TaskStatus to another is allowed.
    Raises InvalidStateTransitionError if the transition is prohibited.
    """
    if from_status == to_status:
        return True

    allowed_targets = VALID_TASK_TRANSITIONS.get(from_status, set())
    if to_status not in allowed_targets:
        raise InvalidStateTransitionError(
            f"Invalid state transition from '{from_status.value}' to '{to_status.value}'.",
            details={
                "from_status": from_status.value,
                "to_status": to_status.value,
                "allowed_transitions": [status.value for status in allowed_targets],
            },
        )
    return True
