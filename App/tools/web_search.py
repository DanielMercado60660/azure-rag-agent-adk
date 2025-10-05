"""
Bing Web Search tool
Implements ADK BaseTool for external information retrieval
"""
import logging
import time
import hashlib
from typing import Any, Dict

from .extended_base_tool import ExtendedBaseTool
from ..core import cache_manager
from ..config import config

logger = logging.getLogger(__name__)


class WebSearchTool(ExtendedBaseTool):
    """
    Bing Web Search for current information.

    ADK Best Practice: Use web search to augment agent knowledge
    with current information beyond training cutoff.
    """

    name = "web_search"
    description = (
        "Search the web for current information and external data. "
        "Use for recent events, news, or information beyond knowledge cutoff."
    )
    timeout_seconds: int = 10

    async def run_async(self, **kwargs) -> Dict[str, Any]:
        """
        Execute web search using Bing Search API.

        ADK Best Practice: Provide external context to agents
        for queries requiring up-to-date information.

        Args:
            query: Search query
            max_results: Maximum results to return (default: 10)

        Returns:
            Dict with status, results, count, and context_items
        """
        start_time = time.time()

        # Extract parameters
        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results", 10)

        # Check cache
        params_hash = hashlib.md5(f"{query}:{max_results}".encode()).hexdigest()
        cached = await cache_manager.get_tool_result(self.name, params_hash)
        if cached:
            logger.info(f"Cache hit for {self.name}: {params_hash[:8]}")
            return cached

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.bing.microsoft.com/v7.0/search",
                    headers={"Ocp-Apim-Subscription-Key": config.BING_SEARCH_KEY},
                    params={"q": query, "count": max_results}
                )

            data = response.json()

            if not data.get("webPages"):
                return {
                    "status": "no_results",
                    "results": [],
                    "count": 0,
                    "tool_cost": 0,
                    "tool_name": self.name,
                    "context_items": []
                }

            results = data["webPages"]["value"]

            # Format context items for agent consumption
            context_items = [
                {
                    "type": "web",
                    "source": self.name,
                    "id": item.get("id"),
                    "content": item.get("snippet"),
                    "metadata": {
                        "name": item.get("name"),
                        "url": item.get("url")
                    }
                }
                for item in results
            ]

            result = {
                "status": "success",
                "tool_name": self.name,
                "results": results,
                "count": len(results),
                "latency_ms": (time.time() - start_time) * 1000,
                "tool_cost": 0.005,  # Approximate Bing Search API cost
                "average_confidence": 0.5,
                "context_items": context_items
            }

            # Cache result
            await cache_manager.set_tool_result(self.name, params_hash, result)

            return result

        except Exception as e:
            logger.error(f"Web search error: {e}")
            return {
                "status": "error",
                "error": str(e),
                "results": [],
                "count": 0,
                "tool_cost": 0,
                "tool_name": self.name,
                "context_items": []
            }
