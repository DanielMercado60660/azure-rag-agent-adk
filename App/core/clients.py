"""
Azure service clients singleton
Follows ADK best practice for resource management and credential handling
"""
import logging
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.cosmos import CosmosClient
from openai import AzureOpenAI
from azure.ai.contentsafety import ContentSafetyClient
import redis.asyncio as redis

from ..config import config

logger = logging.getLogger(__name__)


class AzureClients:
    """
    Singleton for Azure service clients.

    ADK Best Practice: Use singleton pattern for expensive resources
    like API clients to avoid connection overhead in multi-agent systems.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize Azure clients with DefaultAzureCredential"""
        logger.info("Initializing Azure service clients")

        # ADK Best Practice: Use managed identity for secure authentication
        self.credential = DefaultAzureCredential()

        # Azure OpenAI client
        self.openai_client = AzureOpenAI(
            azure_endpoint=config.OPENAI_ENDPOINT,
            api_version=config.OPENAI_API_VERSION,
            azure_ad_token_provider=lambda: self.credential.get_token(
                "https://cognitiveservices.azure.com/.default"
            ).token
        )
        logger.info("Azure OpenAI client initialized")

        # Cosmos DB client
        self.cosmos_client = CosmosClient(config.COSMOS_ENDPOINT, self.credential)
        logger.info("Cosmos DB client initialized")

        # Search Index client
        self.search_index_client = SearchIndexClient(
            endpoint=config.SEARCH_ENDPOINT,
            credential=self.credential
        )
        logger.info("Search Index client initialized")

        # Redis (initialized async on first use)
        self._redis_client = None

        # Content Safety client
        self.content_safety_client = ContentSafetyClient(
            endpoint=config.CONTENT_SAFETY_ENDPOINT,
            credential=self.credential
        )
        logger.info("Content Safety client initialized")

    async def get_redis(self) -> redis.Redis:
        """
        Get Redis client with lazy initialization.

        ADK Best Practice: Lazy-load async resources to avoid
        initialization issues in sync contexts.
        """
        if self._redis_client is None:
            self._redis_client = redis.Redis(
                host=config.REDIS_HOST,
                port=config.REDIS_PORT,
                ssl=config.REDIS_SSL,
                decode_responses=True
            )
            logger.info("Redis client initialized")
        return self._redis_client

    def get_search_client(self, tenant_id: str, index_suffix: str = "kb") -> SearchClient:
        """
        Get tenant-specific Azure AI Search client.

        ADK Best Practice: Create scoped resources per tenant for multi-tenancy.

        Args:
            tenant_id: Tenant identifier
            index_suffix: Index name suffix (default: "kb")

        Returns:
            SearchClient configured for the tenant's index
        """
        index_name = f"{tenant_id}-{index_suffix}"
        return SearchClient(
            endpoint=config.SEARCH_ENDPOINT,
            index_name=index_name,
            credential=self.credential
        )


# Global singleton instance
_clients_instance = None

def get_clients() -> AzureClients:
    """
    Factory function for the AzureClients singleton.
    Initializes the clients on first call.
    """
    global _clients_instance
    if _clients_instance is None:
        _clients_instance = AzureClients()
        # Configure LiteLLM for Azure OpenAI authentication
        # ADK + Azure Best Practice: Set up LiteLLM to use Azure AD tokens
        import os
        if not os.getenv("AZURE_API_KEY"):
            try:
                token = _clients_instance.credential.get_token("https://cognitiveservices.azure.com/.default").token
                os.environ["AZURE_API_KEY"] = token
                logger.info("Set AZURE_API_KEY from DefaultAzureCredential for LiteLLM")
            except Exception as e:
                logger.warning(f"Could not get Azure AD token for LiteLLM: {e}")
    return _clients_instance
