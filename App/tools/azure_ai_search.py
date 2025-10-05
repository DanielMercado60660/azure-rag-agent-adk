"""
Azure AI Search tool with hybrid retrieval
Implements ADK BaseTool with best practices for RAG
"""
import logging
import time
import hashlib
from typing import Any, Dict, List

from google.adk.tools import BaseTool
from azure.search.documents.models import VectorizedQuery

from ..core import clients, cache_manager
from ..config import config

logger = logging.getLogger(__name__)


class AzureAISearchTool(BaseTool):
    """
    Azure AI Search with hybrid vector + BM25 search and semantic reranking.

    ADK Best Practice: Implement BaseTool for integration with ADK agents.
    Use clear name and description for LLM-driven tool selection.
    """

    name = "azure_ai_search"
    description = (
        "Search knowledge base using hybrid vector + BM25 search with semantic reranking. "
        "Use for document retrieval, semantic search, and finding relevant information."
    )

    async def run_async(self, **kwargs) -> Dict[str, Any]:
        """
        Execute hybrid search with semantic reranking.

        ADK Best Practice: Implement run_async for async tool execution
        in agent workflows. Return structured data for agent consumption.

        Args:
            query: Search query text
            tenant_id: Tenant identifier for multi-tenancy
            top_k: Number of results to return (default: 20)
            use_rerank: Enable semantic reranking (default: True)
            filters: Optional OData filter expression

        Returns:
            Dict with status, docs, count, latency_ms, tool_cost, and context_items
        """
        start_time = time.time()

        # Extract parameters
        query = kwargs.get("query", "")
        tenant_id = kwargs.get("tenant_id", "")
        top_k = kwargs.get("top_k", 20)
        use_rerank = kwargs.get("use_rerank", True)
        filters = kwargs.get("filters", None)

        # Check cache
        params_hash = hashlib.md5(f"{query}:{tenant_id}:{top_k}".encode()).hexdigest()
        cached = await cache_manager.get_tool_result(self.name, params_hash)
        if cached:
            logger.info(f"Cache hit for {self.name}: {params_hash[:8]}")
            return cached

        logger.info(f"Cache miss for {self.name}: {params_hash[:8]}")

        try:
            search_client = clients.get_search_client(tenant_id)

            # Generate embeddings
            embedding_response = clients.openai_client.embeddings.create(
                model=config.EMBEDDING_DEPLOYMENT,
                input=query
            )
            query_vector = embedding_response.data[0].embedding

            # Track embedding cost: text-embedding-3-small ~$0.00002 per 1K tokens
            embedding_tokens = (
                embedding_response.usage.total_tokens
                if hasattr(embedding_response, 'usage')
                else 100
            )
            embedding_cost = (embedding_tokens / 1000) * 0.00002

            # Create vector query
            vector_query = VectorizedQuery(
                vector=query_vector,
                k_nearest_neighbors=min(top_k * 2, 100),
                fields="content_vector"
            )

            # ADK + Azure Best Practice: Use semantic ranker for better relevance
            # Critical for sentiment analysis and opinion-based queries
            results = search_client.search(
                search_text=query,
                vector_queries=[vector_query],
                filter=filters,
                top=top_k,
                query_type="semantic",  # Enable L2 semantic reranking
                semantic_configuration_name="default",
                select=["id", "content", "metadata", "tenant_id"]
            )

            # Process results
            docs: List[Dict[str, Any]] = []
            scores: List[float] = []
            for doc in results:
                # Use semantic reranker score if available (0-4 scale)
                reranker_score = doc.get("@search.reranker_score")
                search_score = doc.get("@search.score", 0)
                # Normalize reranker score to 0-1
                score = float(
                    reranker_score / 4.0 if reranker_score is not None else search_score
                )

                payload = {
                    "id": doc.get("id"),
                    "content": doc.get("content", ""),
                    "score": score,
                    "reranker_score": reranker_score,
                    "metadata": doc.get("metadata", {})
                }
                docs.append(payload)
                scores.append(score)

            avg_score = sum(scores) / len(scores) if scores else 0.0

            # Calculate total cost: embedding + search
            search_cost = 0.0001  # Approximate AI Search cost per query
            cost = embedding_cost + search_cost

            # Format context items for agent consumption
            context_items = [
                {
                    "type": "text",
                    "source": self.name,
                    "id": doc.get("id"),
                    "content": doc.get("content", ""),
                    "metadata": doc.get("metadata", {}),
                    "score": doc.get("score", 0)
                }
                for doc in docs
            ]

            result = {
                "status": "success",
                "tool_name": self.name,
                "docs": docs,
                "count": len(docs),
                "latency_ms": (time.time() - start_time) * 1000,
                "tool_cost": cost,
                "average_confidence": avg_score,
                "context_items": context_items
            }

            # Cache result
            await cache_manager.set_tool_result(self.name, params_hash, result)
            return result

        except Exception as e:
            logger.error(f"Azure AI Search error: {e}")
            return {
                "status": "error",
                "error": str(e),
                "docs": [],
                "count": 0,
                "tool_cost": 0,
                "tool_name": self.name,
                "context_items": []
            }
