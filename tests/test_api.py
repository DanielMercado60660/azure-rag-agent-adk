import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

# Thanks to conftest.py, AzureClients is already patched.
# We can now safely import the app at the module level.
from App.api.app import app

# A single TestClient instance can be reused.
client = TestClient(app)

@patch("App.api.app._check_search", new_callable=AsyncMock)
@patch("App.api.app._check_openai", new_callable=AsyncMock)
@patch("App.api.app._check_redis", new_callable=AsyncMock)
def test_health_check_healthy(mock_check_redis, mock_check_openai, mock_check_search):
    """
    Test the /health endpoint when all dependencies are healthy.
    """
    # Arrange
    mock_check_redis.return_value = True
    mock_check_openai.return_value = True
    mock_check_search.return_value = True

    # Act
    response = client.get("/health")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["dependencies"] == {"redis": True, "openai": True, "search": True}

@pytest.mark.parametrize(
    "redis_status, openai_status, search_status",
    [
        (False, True, True),
        (True, False, True),
        (True, True, False),
        (False, False, True),
        (False, True, False),
        (True, False, False),
        (False, False, False),
    ]
)
@patch("App.api.app._check_search", new_callable=AsyncMock)
@patch("App.api.app._check_openai", new_callable=AsyncMock)
@patch("App.api.app._check_redis", new_callable=AsyncMock)
def test_health_check_degraded(
    mock_check_redis, mock_check_openai, mock_check_search,
    redis_status, openai_status, search_status
):
    """
    Test the /health endpoint when any dependency is unhealthy.
    """
    # Arrange
    mock_check_redis.return_value = redis_status
    mock_check_openai.return_value = openai_status
    mock_check_search.return_value = search_status

    expected_dependencies = {
        "redis": redis_status,
        "openai": openai_status,
        "search": search_status,
    }

    # Act
    response = client.get("/health")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["dependencies"] == expected_dependencies