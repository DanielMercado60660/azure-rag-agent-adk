"""
Quality reflection agent
Implements ADK LlmAgent for result sufficiency evaluation
"""
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from ..config import config


def create_reflection_agent() -> LlmAgent:
    """
    Create quality reflection agent.

    ADK Best Practice: Use LlmAgent for evaluating result sufficiency
    in iterative refinement workflows.

    Pattern:
    - Small model (GPT-4o-mini) for fast evaluation
    - Structured output for loop control decisions
    - Gap identification for targeted refinement

    Returns:
        LlmAgent configured for quality reflection
    """
    return LlmAgent(
        name="reflector",
        model=LiteLlm(
            model=f"azure/{config.GPT4O_MINI_DEPLOYMENT}",
            api_base=config.OPENAI_ENDPOINT,
            api_version=config.OPENAI_API_VERSION
        ),
        description="Evaluates result sufficiency",
        instruction="""Evaluate if results are sufficient to answer the query.

Query: {query}
Number of sources: {num_sources}
Average confidence: {avg_confidence}
Source types: {source_types}

Respond with JSON:
{
    "evaluation": "sufficient|insufficient",
    "gaps": ["gap1", "gap2"],
    "reasoning": "explanation"
}""",
        output_schema={
            "type": "object",
            "properties": {
                "evaluation": {"type": "string"},
                "gaps": {"type": "array"},
                "reasoning": {"type": "string"}
            }
        },
        output_key="reflection"
    )
