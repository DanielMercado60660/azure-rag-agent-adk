"""
Multi-layer caching strategy for Azure RAG Agent
Implements ADK best practice for tool result caching to reduce costs
"""
import logging
from typing import Optional, Dict
import json

from .clients import get_clients

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Multi-layer caching strategy using Redis.

    ADK Best Practice: Cache tool results aggressively to reduce
    redundant API calls and improve response times in agent workflows.
    """

    def __init__(self):
        # TTL configuration per cache type (seconds)
        self.ttls = {
            "response": 3600,                # 1 hour for exact responses
            "session": 1800,                 # 30 min for sessions
            "tool_azure_ai_search": 1800,    # 30 min for vector/text search
            "tool_synapse_sql": 300,         # 5 min for SQL results
            "tool_web_search": 600,          # 10 min for web results
            "tool_cosmos_gremlin": 600       # 10 min for graph lookups
        }

    async def get_response(self, query_hash: str) -> Optional[str]:
        """
        Get cached response for exact query match.

        ADK Best Practice: Cache complete responses to avoid
        re-executing entire agent workflows for identical queries.
        """
        redis_client = await get_clients().get_redis()
        cached = await redis_client.get(f"response:{query_hash}")
        if cached:
            logger.info(f"Response cache hit: {query_hash[:8]}")
        return cached

    async def set_response(self, query_hash: str, response: str):
        """Cache complete response"""
        redis_client = await get_clients().get_redis()
        await redis_client.setex(
            f"response:{query_hash}",
            self.ttls["response"],
            response
        )
        logger.info(f"Cached response: {query_hash[:8]}")

    async def get_tool_result(self, tool_name: str, params_hash: str) -> Optional[Dict]:
        """
        Get cached tool result.

        ADK Best Practice: Cache individual tool results to enable
        partial cache hits in multi-tool agent workflows.
        """
        redis_client = await get_clients().get_redis()
        key = f"tool:{tool_name}:{params_hash}"
        cached = await redis_client.get(key)
        if cached:
            logger.info(f"Tool cache hit: {tool_name}:{params_hash[:8]}")
            return json.loads(cached)
        return None

    async def set_tool_result(self, tool_name: str, params_hash: str, result: Dict):
        """Cache tool result with tool-specific TTL"""
        redis_client = await get_clients().get_redis()
        key = f"tool:{tool_name}:{params_hash}"
        ttl = self.ttls.get(f"tool_{tool_name}", 600)
        await redis_client.setex(key, ttl, json.dumps(result))
        logger.info(f"Cached tool result: {tool_name}:{params_hash[:8]}")

    async def get_session(self, session_id: str) -> Optional[Dict]:
        """
        Get session context with automatic TTL extension.

        ADK Best Practice: Store session state in external cache
        for stateless agent deployments.
        """
        redis_client = await get_clients().get_redis()
        key = f"session:{session_id}"
        cached = await redis_client.get(key)
        if cached:
            # Extend TTL on access (sliding expiration)
            await redis_client.expire(key, self.ttls["session"])
            logger.info(f"Session cache hit: {session_id}")
            return json.loads(cached)
        return None

    async def set_session(self, session_id: str, context: Dict):
        """Store session context"""
        redis_client = await get_clients().get_redis()
        await redis_client.setex(
            f"session:{session_id}",
            self.ttls["session"],
            json.dumps(context)
        )
        logger.info(f"Cached session: {session_id}")


# Global cache manager instance
cache_manager = CacheManager()
