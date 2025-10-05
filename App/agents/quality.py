"""
Quality gate agents
Implements ADK BaseAgent for deterministic quality validation and loop control
"""
import logging
from typing import Any, Dict, List

from google.adk.agents import BaseAgent
from google.adk.events import Event, EventActions

from ..config import config

logger = logging.getLogger(__name__)


class QualityGateAgent(BaseAgent):
    """
    Deterministic quality validation agent.

    ADK Best Practice: Use BaseAgent for deterministic logic
    that doesn't require LLM calls but needs agent integration.

    Pattern:
    - Validate against quality thresholds (MIN_RESULTS, MIN_CONFIDENCE, etc.)
    - Update session state with quality metrics
    - Enable downstream decision-making
    """

    def __init__(self):
        super().__init__(
            name="QualityGate",
            description="Validates result quality against thresholds"
        )

    async def _run_async_impl(self, ctx: Any, **kwargs) -> Any:
        """
        DETERMINISTIC quality validation.

        ADK Pattern: Access session state, perform validation,
        update state, yield Event.
        """
        from google.adk.events import Event

        session = ctx.session if hasattr(ctx, 'session') else ctx
        tool_results = session.state.get("tool_results", [])

        # Check quality thresholds
        successful_results = [r for r in tool_results if r.get("status") == "success"]
        num_sources = sum(self._result_count(r) for r in successful_results)
        avg_confidence = self._average_confidence(successful_results)
        num_source_types = len({r.get("tool_name") for r in successful_results if r.get("tool_name")})

        session.state["num_sources"] = num_sources
        session.state["avg_confidence"] = avg_confidence
        session.state["num_source_types"] = num_source_types

        # Quality gate logic
        quality_passed = (
            num_sources >= config.MIN_RESULTS and
            avg_confidence >= config.MIN_CONFIDENCE and
            num_source_types >= config.MIN_SOURCE_TYPES
        )

        session.state["quality_passed"] = quality_passed

        yield Event(
            author=self.name,
            content=f"Quality check: {'PASSED' if quality_passed else 'FAILED'} (sources={num_sources}, confidence={avg_confidence:.2f}, types={num_source_types})"
        )

    def _result_count(self, result: Dict[str, Any]) -> int:
        """Determine how many unique items a tool returned"""
        tool_name = result.get("tool_name")
        if tool_name == "azure_ai_search":
            return len(result.get("docs", []))
        if tool_name == "synapse_sql":
            return len(result.get("rows", []))
        if tool_name == "cosmos_gremlin":
            return result.get("count", 0)
        if tool_name == "web_search":
            return len(result.get("results", []))
        return result.get("count", 0)

    def _average_confidence(self, results: List[Dict[str, Any]]) -> float:
        """Blend confidence scores across tools"""
        confidences = [
            r.get("average_confidence")
            for r in results
            if r.get("average_confidence") is not None
        ]
        return sum(confidences) / len(confidences) if confidences else 0.0


class QualityCheckerAgent(BaseAgent):
    """
    Checks quality status and escalates if sufficient.

    ADK Best Practice: Use EventActions.escalate to control LoopAgent
    termination in iterative refinement workflows.

    Pattern:
    - Check quality_passed state
    - Check reflection evaluation
    - Escalate (exit loop) if both conditions met
    """

    def __init__(self):
        super().__init__(
            name="QualityChecker",
            description="Escalates based on quality status to control loop exit"
        )

    async def _run_async_impl(self, ctx: Any, **kwargs) -> Any:
        """
        Check quality status and escalate if sufficient.

        ADK Pattern: Use EventActions(escalate=True) to exit LoopAgent.
        """
        from google.adk.events import Event, EventActions

        session = ctx.session if hasattr(ctx, 'session') else ctx
        quality_passed = session.state.get("quality_passed", False)
        reflection = session.state.get("reflection", {})

        # Escalate (exit loop) if quality passed AND reflection says sufficient
        sufficient = quality_passed and reflection.get("evaluation") == "sufficient"

        yield Event(
            author=self.name,
            actions=EventActions(escalate=sufficient),
            content=f"Quality check: {'SUFFICIENT - Escalating' if sufficient else 'INSUFFICIENT - Continue iteration'}"
        )
