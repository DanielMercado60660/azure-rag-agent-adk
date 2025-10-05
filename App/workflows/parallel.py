"""
Parallel fan-out/gather workflow
Implements ADK SequentialAgent with parallel tool execution for medium complexity
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


def create_parallel_fanout_gather(tools: Dict[str, BaseTool]) -> SequentialAgent:
    """
    Create parallel fan-out/gather pipeline for medium complexity queries.

    ADK Best Practice: Use ToolExecutionAgent with parallel execution mode
    to run independent tools concurrently, reducing latency.

    Pattern:
    1. Classify query
    2. Plan strategy (with execution_mode="parallel")
    3. Execute tools concurrently (fan-out)
    4. Gather results (fan-in)
    5. Validate quality
    6. Synthesize response

    Key Difference from Sequential:
    - ToolExecutionAgent respects strategy.execution_mode
    - Tools run in parallel when mode="parallel"
    - Reduces total latency for multi-tool queries

    Args:
        tools: Dictionary of available tools

    Returns:
        SequentialAgent configured for medium complexity queries
    """
    return SequentialAgent(
        name="RAGParallelPipeline",
        description="RAG with parallel tool execution for medium complexity",
        sub_agents=[
            create_classifier_agent(),
            create_planner_agent(tools),
            ToolExecutionAgent(tools),  # Executes in parallel based on strategy
            QualityGateAgent(),
            create_synthesizer_agent()
        ]
    )
