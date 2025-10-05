"""
Synapse SQL analytics tool
Implements ADK BaseTool for data warehouse queries
"""
import logging
import time
import hashlib
from typing import Any, Dict, List, Tuple

from google.adk.tools import BaseTool
import pyodbc

from ..core import get_clients, cache_manager
from ..config import config

logger = logging.getLogger(__name__)


class SynapseSQLTool(BaseTool):
    """
    Synapse Serverless SQL analytics tool.

    ADK Best Practice: Use tools for analytical workloads.
    SQL enables aggregations and trend analysis in agent workflows.
    """

    name = "synapse_sql"
    description = (
        "Execute SQL analytics for trends, aggregations, and data analysis. "
        "Use for 'trend', 'graph', 'chart', 'compare' queries."
    )

    async def run_async(self, **kwargs) -> Dict[str, Any]:
        """
        Execute SQL query on Synapse.

        ADK Best Practice: Convert natural language to SQL using LLM,
        then execute safely with parameter binding.

        Args:
            query: Natural language analytics query
            tenant_id: Tenant identifier for data isolation
            limit: Maximum rows to return (default: 1000)

        Returns:
            Dict with status, rows, columns, count, and context_items
        """
        start_time = time.time()

        # Extract parameters
        query = kwargs.get("query", "")
        tenant_id = kwargs.get("tenant_id", "")
        limit = kwargs.get("limit", 1000)

        # Check cache
        params_hash = hashlib.md5(f"{tenant_id}:{query}:{limit}".encode()).hexdigest()
        cached = await cache_manager.get_tool_result(self.name, params_hash)
        if cached:
            logger.info(f"Cache hit for {self.name}: {params_hash[:8]}")
            return cached

        try:
            # Convert NL to SQL using LLM
            sql, llm_cost = await self._nl_to_sql(query, tenant_id)

            # Wrap SQL with LIMIT and tenant filter for safety
            base_sql = sql.strip().rstrip(';')
            wrapped_sql = (
                f"SELECT TOP ({limit}) * FROM (\n"
                f"{base_sql}\n"
                f") AS base_query WHERE tenant_id = ?"
            )

            # Execute SQL
            conn = pyodbc.connect(config.SYNAPSE_DSN, autocommit=True)
            cursor = conn.cursor()

            try:
                cursor.execute(wrapped_sql, tenant_id)
                columns = [column[0] for column in cursor.description]
                raw_rows = cursor.fetchall()
            finally:
                cursor.close()
                conn.close()

            # Sanitize rows for JSON serialization
            rows = [self._sanitize_row(columns, row) for row in raw_rows]

            # Total cost: LLM for NL2SQL + SQL execution
            sql_execution_cost = min(0.0005, 0.00005 * max(len(rows), 1))
            cost = llm_cost + sql_execution_cost

            # Format context items for agent consumption
            context_items = [
                {
                    "type": "table-row",
                    "source": self.name,
                    "id": str(idx),
                    "content": ", ".join(f"{col}={row[col]}" for col in columns),
                    "metadata": row
                }
                for idx, row in enumerate(rows, 1)
            ]

            payload = {
                "status": "success",
                "tool_name": self.name,
                "rows": rows,
                "columns": columns,
                "count": len(rows),
                "latency_ms": (time.time() - start_time) * 1000,
                "tool_cost": cost,
                "average_confidence": 0.8 if rows else 0.0,
                "context_items": context_items
            }

            # Cache result
            await cache_manager.set_tool_result(self.name, params_hash, payload)
            return payload

        except Exception as e:
            logger.error(f"Synapse SQL error: {e}")
            return {
                "status": "error",
                "error": str(e),
                "rows": [],
                "columns": [],
                "count": 0,
                "tool_cost": 0,
                "tool_name": self.name,
                "context_items": []
            }

    async def _nl_to_sql(self, query: str, tenant_id: str) -> Tuple[str, float]:
        """
        Convert natural language to SQL using GPT-4o-mini.

        ADK Best Practice: Use small LLM for query translation
        to minimize cost in tool execution.
        """
        response = get_clients().openai_client.chat.completions.create(
            model=config.GPT4O_MINI_DEPLOYMENT,
            messages=[
                {
                    "role": "system",
                    "content": f"Convert to SQL query for tenant {tenant_id}. Return only the query."
                },
                {"role": "user", "content": query}
            ],
            temperature=0,
            max_tokens=300
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

    def _sanitize_row(self, columns: List[str], row: Tuple[Any, ...]) -> Dict[str, Any]:
        """
        Ensure rows are JSON serializable for caching.

        ADK Best Practice: Normalize tool outputs to JSON-compatible
        types for caching and agent consumption.
        """
        sanitized: Dict[str, Any] = {}
        for column, value in zip(columns, row):
            if isinstance(value, (str, int, float, bool)) or value is None:
                sanitized[column] = value
            else:
                sanitized[column] = str(value)
        return sanitized
