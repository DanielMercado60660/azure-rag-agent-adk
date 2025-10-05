"""
Query classification agent
Implements ADK LlmAgent for query intent and complexity classification
"""
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from pydantic import BaseModel

from ..config import config


class ClassificationOutput(BaseModel):
    """Pydantic model for the classifier's output."""
    intent: str
    complexity: str
    domain: str


def create_classifier_agent() -> LlmAgent:
    """
    Create query classification agent.

    ADK Best Practice: Use LlmAgent with structured output for
    classification tasks to enable dynamic workflow routing.

    Pattern:
    - Small, fast model (GPT-4o-mini) for low latency
    - Structured JSON output for deterministic parsing
    - Clear instruction for consistent classification

    Returns:
        LlmAgent configured for query classification
    """
    return LlmAgent(
        name="classifier",
        model=LiteLlm(
            model=f"azure/{config.GPT4O_MINI_DEPLOYMENT}",
            api_base=config.OPENAI_ENDPOINT,
            api_version=config.OPENAI_API_VERSION
        ),
        description="Classifies queries into intent, complexity, and domain",
        instruction="""Classify the query:
- intent: "lookup" (fact retrieval), "analysis" (data analysis), "generation" (create content)
- complexity: "simple" (1 source, direct), "medium" (2-3 sources), "complex" (4+ sources, synthesis)
- domain: "finance", "ops", "hr", "general"

Respond ONLY with JSON:
{"intent": "...", "complexity": "...", "domain": "..."}""",
        output_schema=ClassificationOutput,
        output_key="classification"
    )
