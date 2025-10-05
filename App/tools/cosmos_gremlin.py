"""
Cosmos DB Gremlin graph tool
Implements ADK BaseTool for knowledge graph queries
"""
import logging
import time
import hashlib
import asyncio
from typing import Any, Dict, List, Tuple

from google.adk.tools import BaseTool
from gremlin_python.driver import client as gremlin_client

from ..core import get_clients, cache_manager
from ..config import config

logger = logging.getLogger(__name__)


class CosmosGremlinTool(BaseTool):
    """
    Cosmos DB Gremlin graph traversal tool.

    ADK Best Practice: Use tools for specialized data sources.
    Graph queries enable relationship discovery in agent workflows.
    """

    name = "cosmos_gremlin"
    description = (
        "Query knowledge graph for relationships and connections. "
        "Use for 'related to', 'connected to', 'impact of' queries."
    )

    async def run_async(self, **kwargs) -> Dict[str, Any]:
        """
        Execute Gremlin graph query.

        ADK Best Practice: Convert natural language to domain-specific
        query language (Gremlin) using LLM, then execute.

        Args:
            query: Natural language query about relationships
            tenant_id: Tenant identifier
            max_depth: Maximum graph traversal depth (default: 3)

        Returns:
            Dict with status, nodes, edges, count, and context_items
        """
        start_time = time.time()

        # Extract parameters
        query = kwargs.get("query", "")
        tenant_id = kwargs.get("tenant_id", "")
        max_depth = kwargs.get("max_depth", 3)

        # Check cache
        params_hash = hashlib.md5(f"{tenant_id}:{query}:{max_depth}".encode()).hexdigest()
        cached = await cache_manager.get_tool_result(self.name, params_hash)
        if cached:
            logger.info(f"Cache hit for {self.name}: {params_hash[:8]}")
            return cached

        try:
            # Convert NL to Gremlin using LLM
            gremlin_query, llm_cost = await self._nl_to_gremlin(query)

            # Create Gremlin client
            graph_client = gremlin_client.Client(
                f"wss://{config.COSMOS_ENDPOINT.split('//')[1].split(':')[0]}.gremlin.cosmos.azure.com:443/",
                'g',
                username=f"/dbs/{config.COSMOS_DATABASE}/colls/{tenant_id}-graph",
                token=await asyncio.to_thread(
                    get_clients().credential.get_token,
                    'https://cosmos.azure.com/.default'
                )
            )

            # Execute query
            try:
                results = graph_client.submit(gremlin_query).all().result()
            finally:
                graph_client.close()

            # Normalize results for agent consumption
            normalized = self._normalize_results(results)

            # Total cost: LLM for NL2Gremlin + Gremlin execution
            gremlin_execution_cost = 0.0002
            cost = llm_cost + gremlin_execution_cost

            payload = {
                "status": "success",
                "tool_name": self.name,
                "nodes": normalized.get("nodes", []),
                "edges": normalized.get("edges", []),
                "count": normalized.get("count", 0),
                "latency_ms": (time.time() - start_time) * 1000,
                "tool_cost": cost,
                "average_confidence": normalized.get("average_confidence", 0.5),
                "context_items": normalized.get("context_items", [])
            }

            # Cache result
            await cache_manager.set_tool_result(self.name, params_hash, payload)
            return payload

        except Exception as e:
            logger.error(f"Cosmos Gremlin error: {e}")
            return {
                "status": "error",
                "error": str(e),
                "nodes": [],
                "edges": [],
                "count": 0,
                "tool_cost": 0,
                "tool_name": self.name,
                "context_items": []
            }

    async def _nl_to_gremlin(self, query: str) -> Tuple[str, float]:
        """
        Convert natural language to Gremlin using GPT-4o-mini.

        ADK Best Practice: Use small, fast LLM for query translation
        to minimize cost and latency in tool execution.
        """
        response = get_clients().openai_client.chat.completions.create(
            model=config.GPT4O_MINI_DEPLOYMENT,
            messages=[
                {
                    "role": "system",
                    "content": "Convert to Gremlin query. Return only the query, no explanations. Limit depth to 3 hops."
                },
                {"role": "user", "content": query}
            ],
            temperature=0,
            max_tokens=200
        )

        # Track LLM cost: GPT-4o-mini ~$0.00015 input, $0.0006 output per 1K tokens
        usage = response.usage
        llm_cost = 0
        if usage:
            llm_cost = (
                (usage.prompt_tokens / 1000 * 0.00015) +
                (usage.completion_tokens / 1000 * 0.0006)
            )

        return response.choices[0].message.content.strip(), llm_cost

    def _normalize_results(self, raw: List[Any]) -> Dict[str, Any]:
        """
        Flatten Gremlin results into agent-friendly format.

        ADK Best Practice: Transform tool outputs into consistent
        structure for agent consumption (context_items pattern).
        """
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        context_items: List[Dict[str, Any]] = []

        for item in raw or []:
            if isinstance(item, dict) and item.get('type') == 'vertex':
                node = {
                    "id": item.get('id'),
                    "label": item.get('label'),
                    "properties": item.get('properties', {})
                }
                nodes.append(node)
                context_items.append({
                    "type": "graph:vertex",
                    "source": self.name,
                    "id": node.get('id'),
                    "content": str(node.get('properties', {})),
                    "metadata": {"label": node.get('label')}
                })
            elif isinstance(item, dict) and item.get('type') == 'edge':
                edge = {
                    "id": item.get('id'),
                    "label": item.get('label'),
                    "outV": item.get('outV'),
                    "inV": item.get('inV'),
                    "properties": item.get('properties', {})
                }
                edges.append(edge)
                context_items.append({
                    "type": "graph:edge",
                    "source": self.name,
                    "id": edge.get('id'),
                    "content": f"{edge.get('outV')} -[{edge.get('label')}]-> {edge.get('inV')}",
                    "metadata": edge.get('properties', {})
                })

        count = len(nodes) + len(edges)
        avg_conf = 0.7 if count else 0.0

        return {
            "nodes": nodes,
            "edges": edges,
            "count": count,
            "average_confidence": avg_conf,
            "context_items": context_items
        }
