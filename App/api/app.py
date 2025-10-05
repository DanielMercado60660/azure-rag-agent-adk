"""
FastAPI application for Azure RAG Agent
Implements REST API with ADK workflow orchestration
"""
import logging
import time
import hashlib
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace

from google.adk.sessions import Session

from .models import QueryRequest, QueryResponse
from ..config import config
from ..core import clients, cache_manager
from ..tools import AzureAISearchTool, CosmosGremlinTool, SynapseSQLTool, WebSearchTool
from ..agents import create_classifier_agent
from ..workflows import (
    create_sequential_pipeline,
    create_parallel_fanout_gather,
    create_iterative_refinement,
)
from ..safety import check_content_safety

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Azure RAG Agent API",
    description="Production RAG agent using Google ADK with Azure services",
    version="1.0.0"
)

# Configure OpenTelemetry for Azure Monitor
if config.APP_INSIGHTS_CONNECTION_STRING:
    configure_azure_monitor(
        connection_string=config.APP_INSIGHTS_CONNECTION_STRING
    )
    logger.info("Azure Monitor telemetry configured")

tracer = trace.get_tracer(__name__)

# Initialize tools (shared across all workflows)
# ADK Best Practice: Reuse tool instances across requests
tools = {
    "azure_ai_search": AzureAISearchTool(),
    "cosmos_gremlin": CosmosGremlinTool(),
    "synapse_sql": SynapseSQLTool(),
    "web_search": WebSearchTool()
}

# Default workflow (dynamically selected per query)
root_agent = create_sequential_pipeline(tools)


@app.post("/query", response_model=QueryResponse)
@tracer.start_as_current_span("process_query")
async def process_query(request: QueryRequest):
    """
    Main query endpoint using ADK workflow orchestration.

    ADK Best Practice: Use dynamic workflow selection based on
    query classification to optimize for cost and latency.

    Pattern:
    1. Check response cache
    2. Initialize ADK session with query context
    3. Run classifier to determine complexity
    4. Select appropriate workflow (sequential/parallel/iterative)
    5. Execute workflow
    6. Validate content safety
    7. Cache and return response

    Args:
        request: QueryRequest with query, tenant_id, etc.

    Returns:
        QueryResponse with answer, sources, metrics

    Raises:
        HTTPException: On content safety violation or processing error
    """
    start_time = time.time()

    # Check response cache
    query_hash = hashlib.md5(f"{request.query}:{request.tenant_id}".encode()).hexdigest()
    cached_response = await cache_manager.get_response(query_hash)
    if cached_response:
        import json
        logger.info(f"Response cache hit: {query_hash[:8]}")
        return JSONResponse(json.loads(cached_response))

    # Initialize ADK session with query context
    # ADK Best Practice: Use Session to maintain state across agent calls
    session = Session(user_id=request.tenant_id)
    session.state.update({
        "query": request.query,
        "tenant_id": request.tenant_id,
        "session_id": request.session_id,
        "user_tier": request.user_tier
    })

    try:
        # Step 1: Run classifier to determine complexity
        # ADK Pattern: Run individual agent for classification
        classifier_agent = create_classifier_agent()
        await classifier_agent.run_async(session, input=request.query)
        classification = session.state.get("classification", {})
        complexity = classification.get("complexity", "medium")

        # Step 2: Select appropriate workflow based on complexity
        # ADK Best Practice: Dynamic workflow selection for optimal performance
        if complexity == "simple":
            selected_agent = create_sequential_pipeline(tools)
            logger.info("Selected Sequential Pipeline for simple query")
        elif complexity == "complex":
            selected_agent = create_iterative_refinement(tools)
            logger.info("Selected Iterative Refinement for complex query")
        else:  # medium
            selected_agent = create_parallel_fanout_gather(tools)
            logger.info("Selected Parallel Fan-Out/Gather for medium query")

        # Step 3: Execute the selected workflow
        # ADK Pattern: run_async with session propagates state
        await selected_agent.run_async(session, input=request.query)

        # Extract results from session state
        final_response = session.state.get("final_response", "")
        classification = session.state.get("classification", {})
        strategy = session.state.get("strategy", {})
        tool_results = session.state.get("tool_results", [])
        cost_meter = session.state.get("cost_meter")

        # Step 4: Content safety check
        # ADK Best Practice: Validate outputs before returning to users
        allowed, reasons = await check_content_safety(final_response)
        if not allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Content policy violation: {', '.join(reasons)}"
            )

        # Build sources payload
        sources_payload = []
        for result in tool_results:
            if result.get("status") != "success":
                continue
            sources_payload.append({
                "tool": result.get("tool_name"),
                "count": _result_count_for_response(result),
                "latency_ms": result.get("latency_ms"),
                "confidence": result.get("average_confidence"),
                "context_items": result.get("context_items", [])
            })

        # Build response
        response = QueryResponse(
            answer=final_response,
            sources=sources_payload,
            cost=cost_meter.spent if cost_meter else 0.0,
            latency_ms=(time.time() - start_time) * 1000,
            classification=classification,
            strategy=strategy
        )

        # Cache response
        await cache_manager.set_response(query_hash, response.json())

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Query processing error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/health")
async def health_check():
    """
    Enhanced health check with dependency validation.

    ADK Best Practice: Implement comprehensive health checks
    for production deployments.

    Returns:
        Dict with overall status and dependency health
    """
    health_status = {
        "status": "healthy",
        "timestamp": time.time(),
        "version": "1.0.0",
        "dependencies": {
            "redis": await _check_redis(),
            "openai": await _check_openai(),
            "search": await _check_search()
        }
    }

    # Overall health is healthy only if all dependencies are healthy
    all_healthy = all(health_status["dependencies"].values())
    health_status["status"] = "healthy" if all_healthy else "degraded"

    return health_status


# Helper functions
def _result_count_for_response(result: Dict[str, Any]) -> int:
    """Count results from tool response"""
    tool_name = result.get("tool_name")
    if tool_name == "azure_ai_search":
        return len(result.get("docs", []))
    if tool_name == "synapse_sql":
        return len(result.get("rows", []))
    if tool_name == "cosmos_gremlin":
        return result.get("count", 0)
    if tool_name == "web_search":
        return len(result.get("results", []))
    return result.get("count", 0)


async def _check_redis() -> bool:
    """Check Redis connectivity"""
    try:
        redis_client = await clients.get_redis()
        await redis_client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False


async def _check_openai() -> bool:
    """Check OpenAI connectivity"""
    try:
        response = clients.openai_client.chat.completions.create(
            model=config.GPT4O_MINI_DEPLOYMENT,
            messages=[{"role": "user", "content": "test"}],
            max_tokens=1
        )
        return response.choices[0].message.content is not None
    except Exception as e:
        logger.error(f"OpenAI health check failed: {e}")
        return False


async def _check_search() -> bool:
    """Check AI Search connectivity"""
    try:
        search_client = clients.get_search_client("test-tenant")
        results = search_client.search(search_text="test", top=1)
        list(results)  # Consume iterator
        return True
    except Exception as e:
        logger.error(f"Search health check failed: {e}")
        return False
