"""
Iterative refinement workflow
Implements ADK LoopAgent pattern for complex queries
"""
from typing import Dict

from google.adk.agents import SequentialAgent, LoopAgent
from google.adk.tools import BaseTool

from ..agents import (
    create_classifier_agent,
    create_planner_agent,
    create_synthesizer_agent,
    create_reflection_agent,
    ToolExecutionAgent,
    QualityGateAgent,
    QualityCheckerAgent,
)
from ..config import config


def create_iterative_refinement(tools: Dict[str, BaseTool]) -> SequentialAgent:
    """
    Create iterative refinement pipeline for complex queries.

    ADK Best Practice: Use LoopAgent for self-improving workflows
    that iterate until quality thresholds are met.

    Pattern:
    1. Classify query
    2. Plan initial strategy
    3. Enter refinement loop:
       a. Execute tools
       b. Validate quality (deterministic)
       c. Reflect on sufficiency (LLM-based)
       d. Check if sufficient (escalate to exit loop)
       e. If insufficient, continue loop with refined strategy
    4. Synthesize final response

    Key ADK Concepts:
    - LoopAgent: Repeats sub_agents until max_iterations or escalation
    - EventActions(escalate=True): Signals loop exit
    - QualityCheckerAgent: Controls loop termination

    Args:
        tools: Dictionary of available tools

    Returns:
        SequentialAgent with embedded LoopAgent for complex queries
    """
    # Define refinement loop
    refinement_loop = LoopAgent(
        name="RefinementLoop",
        description="Iterate until sufficient quality",
        max_iterations=config.MAX_REPLAN_ITERATIONS,
        sub_agents=[
            ToolExecutionAgent(tools),
            QualityGateAgent(),
            create_reflection_agent(),
            QualityCheckerAgent()  # Escalates to exit loop when quality sufficient
        ]
    )

    # Embed loop in sequential pipeline
    return SequentialAgent(
        name="RAGIterativePipeline",
        description="RAG with iterative refinement for complex queries",
        sub_agents=[
            create_classifier_agent(),
            create_planner_agent(),
            refinement_loop,
            create_synthesizer_agent()
        ]
    )
