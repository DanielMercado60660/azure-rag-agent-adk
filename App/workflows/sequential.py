"""
Sequential pipeline workflow
Implements ADK SequentialAgent pattern for simple queries
"""
from typing import Dict

from google.adk.agents import SequentialAgent
from google.adk.tools import BaseTool

from ..agents import (
    create_classifier_agent,
    create_planner_agent,
    create_synthesizer_agent,
    ToolExecutionAgent,
    QualityGateAgent,
)


def create_sequential_pipeline(tools: Dict[str, BaseTool]) -> SequentialAgent:
    """
    Create sequential pipeline for simple queries.

    ADK Best Practice: Use SequentialAgent for linear workflows
    where each agent depends on the previous agent's output.

    Pattern:
    1. Classify query (intent, complexity, domain)
    2. Plan execution strategy (tools, mode)
    3. Execute tools sequentially
    4. Validate quality gates
    5. Synthesize final response

    Args:
        tools: Dictionary of available tools

    Returns:
        SequentialAgent configured for simple query processing
    """
    return SequentialAgent(
        name="RAGSequentialPipeline",
        description="Sequential RAG pipeline for simple queries",
        sub_agents=[
            create_classifier_agent(),
            create_planner_agent(tools),
            ToolExecutionAgent(tools),
            QualityGateAgent(),
            create_synthesizer_agent()
        ]
    )
