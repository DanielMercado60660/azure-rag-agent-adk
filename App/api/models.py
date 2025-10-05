"""
API request/response models
Pydantic models for FastAPI endpoints
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class QueryRequest(BaseModel):
    """
    Query request model.

    ADK Best Practice: Define clear API contracts for agent inputs.
    """
    query: str
    tenant_id: str
    session_id: Optional[str] = None
    user_tier: str = "free"  # free, pro, enterprise


class QueryResponse(BaseModel):
    """
    Query response model.

    ADK Best Practice: Return structured responses with metadata
    for observability and debugging.
    """
    answer: str
    sources: List[Dict[str, Any]]
    cost: float
    latency_ms: float
    classification: Dict[str, str]
    strategy: Dict[str, Any]
