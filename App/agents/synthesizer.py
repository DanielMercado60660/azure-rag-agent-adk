"""
Response synthesis agent
Implements ADK LlmAgent for final answer generation
"""
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from ..config import config


def create_synthesizer_agent() -> LlmAgent:
    """
    Create response synthesis agent.

    ADK Best Practice: Use LlmAgent for final synthesis to generate
    grounded, citation-rich responses from retrieved context.

    Pattern:
    - Powerful model (GPT-4o) for high-quality synthesis
    - Context-grounded generation with citations
    - Clear guidelines for factual, helpful responses

    Returns:
        LlmAgent configured for response synthesis
    """
    return LlmAgent(
        name="synthesizer",
        model=LiteLlm(
            model=f"azure/{config.GPT4O_DEPLOYMENT}",
            api_base=config.OPENAI_ENDPOINT,
            api_version=config.OPENAI_API_VERSION
        ),
        description="Synthesizes final response with citations",
        instruction="""Synthesize a response using the retrieved context.

Query: {query}

Context:
{context}

Guidelines:
- Answer directly and concisely
- Use ONLY information from context
- Include citations: [source_1], [source_2]
- If context insufficient, state clearly
- Professional, helpful tone

Format:
1. Direct answer
2. Supporting details
3. Citations""",
        output_key="final_response"
    )
