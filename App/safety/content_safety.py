"""
Azure AI Content Safety integration
Implements content moderation for agent responses
"""
import logging
from typing import Tuple, List

from azure.ai.contentsafety.models import AnalyzeTextOptions

from ..core import get_clients

logger = logging.getLogger(__name__)


async def check_content_safety(text: str) -> Tuple[bool, List[str]]:
    """
    Check text with Azure AI Content Safety.

    ADK Best Practice: Validate agent outputs before returning to users
    to ensure compliance with content policies.

    Pattern:
    - Check all safety categories (hate, self-harm, sexual, violence)
    - Use severity thresholds (0-7 scale, fail at >=4)
    - Fail open for availability (allow on API errors)

    Args:
        text: Text to analyze

    Returns:
        Tuple of (allowed: bool, reasons: List[str])
        - allowed: True if content passes safety checks
        - reasons: List of safety violations if any
    """
    try:
        request = AnalyzeTextOptions(text=text)
        result = get_clients().content_safety_client.analyze_text(request)

        # Check severity thresholds
        reasons = []
        allowed = True

        for category in [
            result.hate_result,
            result.self_harm_result,
            result.sexual_result,
            result.violence_result
        ]:
            if category.severity >= 4:  # Medium-High or High severity
                allowed = False
                reasons.append(f"{category.category}: severity {category.severity}")

        if not allowed:
            logger.warning(f"Content safety violation: {', '.join(reasons)}")

        return allowed, reasons

    except Exception as e:
        logger.error(f"Content safety error: {e}")
        # Fail open for availability - allow content if safety check fails
        # ADK Best Practice: Balance safety with availability based on use case
        return True, []
