"""
Configuration and budget settings for Azure RAG Agent
Follows ADK best practices for environment-based configuration
"""
from dataclasses import dataclass, field
from typing import Dict
import os


@dataclass
class Config:
    """
    Central configuration for Azure services and ADK settings.

    ADK Best Practice: Use environment variables for sensitive configuration
    and provide sensible defaults for development.
    """
    # Azure OpenAI
    OPENAI_ENDPOINT: str = os.getenv(
        "AZURE_OPENAI_ENDPOINT",
        "https://<tenant>.openai.azure.com/"
    )
    OPENAI_API_VERSION: str = os.getenv(
        "AZURE_OPENAI_API_VERSION",
        "2024-02-15-preview"
    )
    GPT4O_DEPLOYMENT: str = os.getenv("AZURE_GPT4O_DEPLOYMENT", "gpt-4o")
    GPT4O_MINI_DEPLOYMENT: str = os.getenv("AZURE_GPT4O_MINI_DEPLOYMENT", "gpt-4o-mini")
    EMBEDDING_DEPLOYMENT: str = os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")

    # Azure AI Search
    SEARCH_ENDPOINT: str = os.getenv(
        "AZURE_SEARCH_ENDPOINT",
        "https://<tenant>-search.search.windows.net"
    )

    # Cosmos DB
    COSMOS_ENDPOINT: str = os.getenv(
        "AZURE_COSMOS_ENDPOINT",
        "https://<tenant>-cosmos.documents.azure.com:443/"
    )
    COSMOS_DATABASE: str = os.getenv("AZURE_COSMOS_DATABASE", "rag_agent")

    # Synapse
    SYNAPSE_DSN: str = os.getenv(
        "AZURE_SYNAPSE_DSN",
        "DRIVER={ODBC Driver 17 for SQL Server};SERVER=<tenant>-synapse.sql.azuresynapse.net;DATABASE=analytics;Authentication=ActiveDirectoryMsi"
    )

    # Redis
    REDIS_HOST: str = os.getenv(
        "AZURE_REDIS_HOST",
        "<tenant>-redis.redisenterprise.cache.azure.net"
    )
    REDIS_PORT: int = int(os.getenv("AZURE_REDIS_PORT", "10000"))
    REDIS_SSL: bool = os.getenv("AZURE_REDIS_SSL", "true").lower() == "true"
    REDIS_IS_ENTERPRISE: bool = os.getenv("AZURE_REDIS_IS_ENTERPRISE", "true").lower() == "true"

    # Content Safety
    CONTENT_SAFETY_ENDPOINT: str = os.getenv(
        "AZURE_CONTENT_SAFETY_ENDPOINT",
        "https://<tenant>-safety.cognitiveservices.azure.com/"
    )

    # Bing Search
    BING_SEARCH_KEY: str = os.getenv("BING_SEARCH_KEY", "")

    # Budget limits per tier (USD)
    BUDGET_SIMPLE: float = float(os.getenv("BUDGET_SIMPLE", "0.001"))
    BUDGET_MEDIUM: float = float(os.getenv("BUDGET_MEDIUM", "0.005"))
    BUDGET_COMPLEX: float = float(os.getenv("BUDGET_COMPLEX", "0.010"))
    MAX_QUERY_BUDGET: float = float(os.getenv("MAX_QUERY_BUDGET", "0.010"))

    # Timeouts (seconds) - ADK Best Practice: Set reasonable timeouts for tool execution
    TIMEOUT_SEARCH: float = float(os.getenv("TIMEOUT_SEARCH", "0.5"))
    TIMEOUT_GRAPH: float = float(os.getenv("TIMEOUT_GRAPH", "1.0"))
    TIMEOUT_SQL: float = float(os.getenv("TIMEOUT_SQL", "2.0"))
    TIMEOUT_WEB: float = float(os.getenv("TIMEOUT_WEB", "2.0"))
    TIMEOUT_TOTAL: float = float(os.getenv("TIMEOUT_TOTAL", "5.0"))

    # Quality gates - ADK Best Practice: Define quality thresholds for agent outputs
    MIN_RESULTS: int = int(os.getenv("MIN_RESULTS", "2"))
    MIN_CONFIDENCE: float = float(os.getenv("MIN_CONFIDENCE", "0.6"))
    MIN_SOURCE_TYPES: int = int(os.getenv("MIN_SOURCE_TYPES", "1"))
    MAX_REPLAN_ITERATIONS: int = int(os.getenv("MAX_REPLAN_ITERATIONS", "3"))

    # Application Insights
    APP_INSIGHTS_CONNECTION_STRING: str = os.getenv(
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
        ""
    )

    def __post_init__(self):
        """Validate configuration values"""
        if not self.OPENAI_ENDPOINT.startswith('https://'):
            raise ValueError("OPENAI_ENDPOINT must be a valid HTTPS URL")
        if not self.SEARCH_ENDPOINT.startswith('https://'):
            raise ValueError("SEARCH_ENDPOINT must be a valid HTTPS URL")
        if not self.COSMOS_ENDPOINT.startswith('https://'):
            raise ValueError("COSMOS_ENDPOINT must be a valid HTTPS URL")
        if self.MIN_CONFIDENCE < 0 or self.MIN_CONFIDENCE > 1:
            raise ValueError("MIN_CONFIDENCE must be between 0 and 1")
        if self.MIN_RESULTS < 1:
            raise ValueError("MIN_RESULTS must be at least 1")
        if self.MAX_REPLAN_ITERATIONS < 1:
            raise ValueError("MAX_REPLAN_ITERATIONS must be at least 1")


@dataclass
class BudgetTier:
    """
    Budget tier configuration for cost control.

    ADK Best Practice: Implement budget controls to prevent runaway costs
    in multi-agent systems with tool calls.
    """
    total_usd: float
    max_tool_calls: int
    max_llm_calls: int


# Budget tier presets
BUDGETS: Dict[str, BudgetTier] = {
    "simple": BudgetTier(0.001, 1, 1),
    "medium": BudgetTier(0.005, 3, 2),
    "complex": BudgetTier(0.010, 5, 3),
}

# Global config instance
config = Config()
