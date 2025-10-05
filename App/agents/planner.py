"""
Strategy planning agent
Implements ADK LlmAgent for execution strategy planning
"""
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import BaseTool
from pydantic import BaseModel
from typing import Dict, List

from ..config import config


class PlannerOutput(BaseModel):
    """Pydantic model for the planner's output."""
    strategy_type: str
    tools: List[str]
    execution_mode: str
    reasoning: str


def create_planner_agent(tools: Dict[str, BaseTool]) -> LlmAgent:
    """
    Create strategy planning agent.

    ADK Best Practice: Use LlmAgent for dynamic planning to enable
    adaptive workflow execution based on query characteristics.

    Pattern:
    - Powerful model (GPT-4o) for strategic reasoning
    - Structured output for workflow orchestration
    - Budget-aware planning with tool selection

    Returns:
        LlmAgent configured for strategy planning
    """
    # ADK Best Practice: Dynamically generate tool list for planner prompt
    # to ensure it's always up-to-date and reduce maintenance.
    tool_descriptions = "\n".join(
        [f"- {name}: {tool.description}" for name, tool in tools.items()]
    )

    instruction = f"""Create execution strategy for the query: {{query}}

Classification: {{classification}}
Max tools allowed: {{max_tools}}

Available tools:
{tool_descriptions}

Strategy types:
- direct: Single tool, simple lookup
- multi-source: 2-3 tools for comprehensive answer
- iterative: Sequential with refinement

Execution modes:
- sequential: Tools run in order
- parallel: Independent tools run simultaneously

Respond ONLY with JSON:
{{
    "strategy_type": "direct|multi-source|iterative",
    "tools": ["tool1", "tool2"],
    "execution_mode": "sequential|parallel",
    "reasoning": "brief explanation"
}}"""

    return LlmAgent(
        name="planner",
        model=LiteLlm(
            model=f"azure/{config.GPT4O_DEPLOYMENT}",
            api_base=config.OPENAI_ENDPOINT,
            api_version=config.OPENAI_API_VERSION
        ),
        description="Creates execution strategy within budget constraints",
        instruction=instruction,
        output_schema=PlannerOutput,
        output_key="strategy"
    )
