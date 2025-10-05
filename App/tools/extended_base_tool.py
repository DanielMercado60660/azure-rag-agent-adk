"""
Extended base tool for application-specific functionality
"""
from google.adk.tools import BaseTool


class ExtendedBaseTool(BaseTool):
    """
    Extends ADK BaseTool with app-specific properties.

    New properties:
    - timeout_seconds: Timeout for tool execution
    """
    timeout_seconds: int = 20  # Default timeout