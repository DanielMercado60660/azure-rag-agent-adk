"""
Cost tracking and budget enforcement
Implements ADK best practice for cost control in agent systems
"""
import logging
from dataclasses import dataclass, field
from typing import Dict
import json

logger = logging.getLogger(__name__)


@dataclass
class CostMeter:
    """
    Tracks costs per query for budget enforcement.

    ADK Best Practice: Implement cost tracking to prevent runaway
    expenses in multi-agent systems with LLM calls and tool executions.

    Pattern:
    1. Set budget limit at query start based on complexity tier
    2. Track costs per category (tools, LLM calls, embeddings)
    3. Enforce limits before each operation
    4. Log cost breakdown for observability
    """
    limit: float
    spent: float = 0.0
    tool_calls: int = 0
    llm_calls: int = 0
    breakdown: Dict[str, float] = field(default_factory=dict)

    def charge(self, category: str, amount: float):
        """
        Add cost and track by category.

        ADK Best Practice: Track costs granularly to identify
        expensive operations and optimize agent workflows.

        Args:
            category: Cost category (e.g., tool name, "embedding", "llm")
            amount: Cost in USD
        """
        self.spent += amount
        self.breakdown[category] = self.breakdown.get(category, 0) + amount

        # Log cost meter updates for observability
        logger.info('cost_meter %s', json.dumps({
            "spent": self.spent,
            "limit": self.limit,
            "breakdown": self.breakdown,
            "tool_calls": self.tool_calls,
            "llm_calls": self.llm_calls
        }))

    def allow_tool(self, max_tools: int) -> bool:
        """
        Check if we can make another tool call.

        ADK Best Practice: Enforce limits before tool execution
        to prevent budget overruns in complex agent workflows.
        """
        return self.tool_calls < max_tools and self.spent < self.limit

    def allow_llm(self, max_llm: int) -> bool:
        """
        Check if we can make another LLM call.

        ADK Best Practice: Control LLM call count in addition to cost
        to prevent excessive iterations in agent loops.
        """
        return self.llm_calls < max_llm and self.spent < self.limit
