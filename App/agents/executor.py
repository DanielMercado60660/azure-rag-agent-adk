"""
Tool execution agent
Implements ADK BaseAgent for orchestrating tool calls with budget and circuit breaker controls
"""
import logging
import asyncio
from typing import Any, Dict, List

from google.adk.agents import BaseAgent
from google.adk.tools import BaseTool
from google.adk.events import Event

from ..core import circuit_breaker, CostMeter
from ..config import BUDGETS, config

logger = logging.getLogger(__name__)


class ToolExecutionAgent(BaseAgent):
    """
    Executes tools with ADK integration, circuit breakers, and budgets.

    ADK Best Practice: Implement BaseAgent for custom orchestration logic
    that goes beyond standard LlmAgent capabilities.

    Features:
    - Parallel and sequential tool execution
    - Budget tracking and enforcement
    - Circuit breaker pattern for resilience
    - Timeout enforcement per tool
    - Quality gate validation
    """
    tools: Dict[str, BaseTool]

    def __init__(self, tools: Dict[str, BaseTool]):
        super().__init__(
            name="executor",
            description="Executes tools with budget tracking and circuit breaking",
            tools=tools
        )

    async def _run_async_impl(self, ctx: Any, **kwargs) -> Any:
        """
        Execute tools based on strategy.

        ADK Pattern: Access session via ctx.session, yield Events for updates.

        Args:
            ctx: ADK context with session

        Yields:
            Event with execution status and metrics
        """
        from google.adk.events import Event

        # Access session state (ADK pattern)
        session = ctx.session if hasattr(ctx, 'session') else ctx
        query = session.state.get("query", "")
        tenant_id = session.state.get("tenant_id", "")
        strategy = session.state.get("strategy", {})

        # Initialize budget if not already set
        if "cost_meter" not in session.state:
            classification = session.state.get("classification", {})
            complexity = classification.get("complexity", "medium")
            budget_tier = BUDGETS.get(complexity, BUDGETS["medium"])
            cost_meter = CostMeter(limit=budget_tier.total_usd)
            session.state["budget_tier"] = budget_tier
            session.state["cost_meter"] = cost_meter
            session.state["max_tools"] = budget_tier.max_tool_calls
        else:
            cost_meter = session.state.get("cost_meter")
            budget_tier = session.state.get("budget_tier")

        tools_to_run = strategy.get("tools", [])
        execution_mode = strategy.get("execution_mode", "sequential")

        all_results = []
        successful_results: List[Dict[str, Any]] = []

        # ADK Pattern: True parallel or sequential execution
        if execution_mode == "parallel":
            # Parallel fan-out: Execute tools concurrently
            tasks = []
            for tool_name in tools_to_run:
                if not cost_meter.allow_tool(budget_tier.max_tool_calls):
                    logger.warning(f"Budget limit reached, skipping {tool_name}")
                    break
                if tool_name in self.tools and circuit_breaker.is_closed(tool_name):
                    tasks.append(
                        self._execute_tool(tool_name, query, tenant_id, cost_meter, **kwargs)
                    )

            # Fan-in: Gather results
            gathered = await asyncio.gather(*tasks, return_exceptions=True)
            for result in gathered:
                if isinstance(result, Exception):
                    logger.error(f"Tool execution exception: {result}")
                    all_results.append({"status": "error", "error": str(result)})
                else:
                    all_results.append(result)
                    if result.get("status") == "success":
                        successful_results.append(result)
        else:
            # Sequential execution
            for tool_name in tools_to_run:
                if not cost_meter.allow_tool(budget_tier.max_tool_calls):
                    logger.warning(f"Budget limit reached, skipping {tool_name}")
                    break

                if tool_name in self.tools and circuit_breaker.is_closed(tool_name):
                    result = await self._execute_tool(tool_name, query, tenant_id, cost_meter, **kwargs)
                    all_results.append(result)
                    if result.get("status") == "success":
                        successful_results.append(result)

        # Collect and render context
        context_items = self._collect_context(successful_results)
        context_str = self._render_context(context_items)
        avg_confidence = self._average_confidence(successful_results)

        # Update session state
        session.state["tool_results"] = all_results
        session.state["context_items"] = context_items
        session.state["context"] = context_str
        session.state["result_metrics"] = {
            "total_items": sum(self._result_count(r) for r in successful_results),
            "average_confidence": avg_confidence,
            "source_types": list({r.get("tool_name") for r in successful_results})
        }
        session.state["num_sources"] = session.state["result_metrics"]["total_items"]
        session.state["avg_confidence"] = avg_confidence
        session.state["source_types"] = session.state["result_metrics"]["source_types"]
        session.state["quality_passed"] = self._check_quality_gate(successful_results, avg_confidence)

        # ADK pattern: yield event with state updates
        yield Event(
            author=self.name,
            content=f"Executed {len(successful_results)} tools successfully. Quality: {'PASSED' if session.state['quality_passed'] else 'FAILED'}"
        )

    async def _execute_tool(
        self,
        tool_name: str,
        query: str,
        tenant_id: str,
        cost_meter: CostMeter,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute a single tool with error handling and circuit breaker.

        ADK Best Practice: Implement timeout enforcement and error handling
        for tool execution to ensure resilient agent workflows.
        """
        tool = self.tools[tool_name]
        try:
            # Check circuit breaker
            if not circuit_breaker.is_closed(tool_name):
                logger.warning(f"Circuit open for {tool_name}")
                return {"status": "circuit_open", "tool_name": tool_name}

            # Use tool-defined timeout (ADK best practice)
            timeout = getattr(tool, "timeout_seconds", 20)  # Default to 20s

            # Execute tool with timeout
            result = await asyncio.wait_for(
                tool.run_async(
                    query=query,
                    tenant_id=tenant_id,
                    **kwargs
                ),
                timeout=timeout
            )

            # Track cost and success
            cost_meter.charge(tool_name, result.get("tool_cost", 0))
            cost_meter.tool_calls += 1
            circuit_breaker.record_success(tool_name)

            result.setdefault("tool_name", tool_name)
            return result

        except asyncio.TimeoutError:
            logger.warning(f"Tool {tool_name} timed out after {timeout}s")
            circuit_breaker.record_failure(tool_name)
            return {
                "status": "timeout",
                "tool_name": tool_name,
                "error": f"Timeout after {timeout}s"
            }
        except Exception as e:
            logger.error(f"Tool {tool_name} error: {e}")
            circuit_breaker.record_failure(tool_name)
            return {"status": "error", "tool_name": tool_name, "error": str(e)}

    def _check_quality_gate(self, successful_results: List[Dict], avg_confidence: float) -> bool:
        """Check if results meet quality thresholds"""
        total_items = sum(self._result_count(r) for r in successful_results)
        if total_items < config.MIN_RESULTS:
            return False

        source_types = {r.get("tool_name", "") for r in successful_results if r.get("tool_name")}
        if len(source_types) < config.MIN_SOURCE_TYPES:
            return False

        if avg_confidence < config.MIN_CONFIDENCE:
            return False

        return True

    def _collect_context(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Flatten context items from tool responses"""
        items: List[Dict[str, Any]] = []
        for result in results:
            for item in result.get("context_items", []) or []:
                if "source" not in item:
                    item["source"] = result.get("tool_name")
                items.append(item)
        return items

    def _render_context(self, items: List[Dict[str, Any]]) -> str:
        """Render context snippets into prompt-ready text"""
        if not items:
            return ""
        lines: List[str] = []
        for idx, item in enumerate(items, 1):
            source = item.get("source", "tool")
            identifier = item.get("id")
            content = item.get("content", "")
            prefix = f"[{idx}] ({source})"
            if identifier:
                prefix = f"{prefix} {identifier}"
            lines.append(f"{prefix}: {content}")
        return "\n".join(lines)

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
