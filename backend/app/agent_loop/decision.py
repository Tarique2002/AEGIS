"""Decision Engine evaluating observation data, reflection, and budgets to decide next actions."""

from app.agent_loop.budget import AgentBudget
from app.agent_loop.guardrails import ProgressTracker
from app.agent_loop.observation import ObservationBuilder
from app.agent_loop.policies import AgentLoopPolicy
from app.agent_loop.schemas import AgentDecision, AgentObservation, DecisionType, LLMDecisionOutput
from app.core.logging import get_logger
from app.llm.base import LLMProvider
from app.schemas.common import ChatMessage, ChatRole

logger = get_logger("aegis.agent_loop.decision")


class DecisionEngine:
    """
    Decides the next iteration action (CONTINUE, COMPLETE, REPLAN, RETRY, WAIT, FAIL, SAFETY_STOP)
    using deterministic safety rules and structured LLM inference with deterministic fallback.
    """

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        policy: AgentLoopPolicy | None = None,
        observation_builder: ObservationBuilder | None = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.policy = policy or AgentLoopPolicy()
        self.observation_builder = observation_builder or ObservationBuilder(policy=self.policy)

    def _evaluate_deterministic_rules(
        self,
        observation: AgentObservation,
        tracker: ProgressTracker,
        budget: AgentBudget,
    ) -> AgentDecision | None:
        """Evaluate hard deterministic termination rules before calling LLM."""
        # 1. Check stagnation
        is_stagnant, reason = tracker.check_stagnation()
        if is_stagnant:
            return AgentDecision(
                iteration_number=observation.iteration_number,
                decision_type=DecisionType.FAIL,
                rationale=f"Stagnation detected: {reason}",
                confidence=1.0,
                stop_reason=reason,
            )

        # 2. Check evaluation score completion threshold
        if observation.evaluation_result and observation.evaluation_result.passed:
            if (
                observation.evaluation_result.overall_score
                >= self.policy.completion_score_threshold
            ):
                score_val = observation.evaluation_result.overall_score
                return AgentDecision(
                    iteration_number=observation.iteration_number,
                    decision_type=DecisionType.COMPLETE,
                    rationale=(
                        f"Evaluation passed with score {score_val:.2f} "
                        f"(>= {self.policy.completion_score_threshold}). Objective satisfied."
                    ),
                    confidence=1.0,
                    stop_reason="Objective satisfied and validated by evaluation.",
                )

        # 3. Check execution outcome if single-pass calculation succeeded with no errors
        if (
            observation.execution_results
            and observation.execution_results.status.value == "COMPLETED"
            and observation.execution_results.final_output is not None
            and not observation.active_errors
            and not observation.evaluation_result
        ):
            return AgentDecision(
                iteration_number=observation.iteration_number,
                decision_type=DecisionType.COMPLETE,
                rationale="Execution plan completed successfully with final output.",
                confidence=1.0,
                stop_reason="Plan executed successfully.",
            )

        return None

    async def make_decision(
        self,
        observation: AgentObservation,
        tracker: ProgressTracker,
        budget: AgentBudget,
        objective: str,
    ) -> AgentDecision:
        """
        Produce a structured, bounded decision for the next loop step.
        """
        # 1. Deterministic Rule Pass
        rule_decision = self._evaluate_deterministic_rules(observation, tracker, budget)
        if rule_decision:
            return rule_decision

        # 2. LLM Decision Proposal Pass (if provider configured)
        if self.llm_provider:
            prompt_context = self.observation_builder.format_prompt_context(observation, objective)
            prompt = f"""You are the Decision Engine of an autonomous agent loop.
Analyze current observation, progress, reflection, and remaining budget to decide the next action.

Available Decision Types:
- COMPLETE: If objective is fully satisfied and output is validated.
- REPLAN: If previous execution failed, was incomplete, or reflection suggests revised strategy.
- RETRY: If a transient failure occurred and retries remain.
- CONTINUE: If further execution of existing strategy is required.
- FAIL: If objective cannot be achieved or unrecoverable errors occurred.
- SAFETY_STOP: If safety policies or constraints are violated.

Context:
{prompt_context}

Return a valid JSON object matching the required schema.
"""
            messages = [
                ChatMessage(
                    role=ChatRole.SYSTEM,
                    content=(
                        "You are an expert autonomous loop controller decision engine. "
                        "Return only structured JSON proposing the next action."
                    ),
                ),
                ChatMessage(role=ChatRole.USER, content=prompt),
            ]

            try:
                budget.consume_llm_call(1)
                res = await self.llm_provider.generate_structured(
                    messages=messages,
                    response_model=LLMDecisionOutput,
                    temperature=0.0,
                )
                output: LLMDecisionOutput = res.data

                # Guard: ensure valid decision type
                return AgentDecision(
                    iteration_number=observation.iteration_number,
                    decision_type=output.decision_type,
                    rationale=output.rationale,
                    confidence=output.confidence,
                    next_plan_required=output.next_plan_required
                    or output.decision_type == DecisionType.REPLAN,
                    stop_reason=output.stop_reason,
                    selected_actions=output.suggested_actions,
                )
            except Exception as exc:
                logger.warning(
                    f"LLM decision inference failed or invalid; falling back to rules: {exc}"
                )

        # 3. Deterministic Fallback Logic
        return self._deterministic_fallback_decision(observation)

    def _deterministic_fallback_decision(self, observation: AgentObservation) -> AgentDecision:
        """Deterministic decision logic when LLM is unavailable or fails."""
        if observation.active_errors or (
            observation.execution_results and observation.execution_results.status.value == "FAILED"
        ):
            # If reflection exists, propose replanning
            return AgentDecision(
                iteration_number=observation.iteration_number,
                decision_type=DecisionType.REPLAN,
                rationale="Execution errors encountered; replanning with updated observation.",
                confidence=0.8,
                next_plan_required=True,
            )

        if (
            observation.execution_results
            and observation.execution_results.status.value == "COMPLETED"
        ):
            return AgentDecision(
                iteration_number=observation.iteration_number,
                decision_type=DecisionType.COMPLETE,
                rationale="Plan execution succeeded.",
                confidence=0.9,
                stop_reason="Execution completed.",
            )

        # Initial pass -> Replan / create initial plan
        return AgentDecision(
            iteration_number=observation.iteration_number,
            decision_type=DecisionType.REPLAN,
            rationale="Initial iteration: generating execution plan.",
            confidence=1.0,
            next_plan_required=True,
        )
