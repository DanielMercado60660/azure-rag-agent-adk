"""
Azure Multi-Tenant RAG Agent with ADK - Production Implementation
=================================================================

Architecture:
- Edge: Front Door (TLS) + API Management (Auth/Quotas)
- Orchestration: Container Apps with FastAPI + ADK agents
- Caching: Redis (response, session, tool, semantic)
- Retrieval: AI Search, Cosmos Gremlin, Synapse SQL (all Private Link)
- Models: Azure ML (per-tenant FT) + Azure OpenAI (foundations)
- Safety: Content Safety + Purview
- Observability: App Insights + Monitor + Log Analytics

Google ADK Best Practices:
- Modular agent composition with SequentialAgent, ParallelAgent, LoopAgent
- LiteLLM wrapper for Azure OpenAI integration
- BaseTool implementation for custom tools
- Session-based state management
- Dynamic workflow selection based on query complexity
- Budget tracking and circuit breakers for resilience

Project Structure:
- config/: Configuration and budget settings
- core/: Infrastructure (clients, cache, circuit breakers, cost tracking)
- tools/: ADK BaseTool implementations (Azure AI Search, Cosmos, Synapse, Bing)
- agents/: ADK agent factories (classifier, planner, executor, synthesizer, etc.)
- workflows/: ADK workflow patterns (sequential, parallel, iterative)
- safety/: Content safety validation
- api/: FastAPI application and models
"""
import logging
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import FastAPI app from api module
from App.api import app

# Import tools for ADK CLI export
from App.tools import AzureAISearchTool, CosmosGremlinTool, SynapseSQLTool, WebSearchTool
from App.workflows import create_sequential_pipeline

# Initialize tools for ADK CLI
tools = {
    "azure_ai_search": AzureAISearchTool(),
    "cosmos_gremlin": CosmosGremlinTool(),
    "synapse_sql": SynapseSQLTool(),
    "web_search": WebSearchTool()
}

# Export root agent for ADK CLI
# ADK Best Practice: Export ROOT_AGENT for CLI testing and development
ROOT_AGENT = create_sequential_pipeline(tools)

if __name__ == "__main__":
    logger.info("Starting Azure RAG Agent with ADK")
    logger.info("Architecture: Multi-tenant RAG with dynamic workflow selection")
    logger.info("ADK Workflows: Sequential (simple) | Parallel (medium) | Iterative (complex)")

    # Run FastAPI application
    uvicorn.run(app, host="0.0.0.0", port=8080)
