import pytest
from unittest.mock import patch

@pytest.fixture(autouse=True)
def mock_azure_clients():
    """
    This fixture automatically patches the AzureClients class for all tests,
    preventing any actual calls to Azure services.
    """
    with patch("App.core.clients.AzureClients") as mock:
        yield mock