#!/usr/bin/env python3
"""Create per-tenant Cosmos DB containers for SQL + Gremlin workloads."""

import argparse
import logging
import os
import time
from typing import Optional

import httpx
from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient, PartitionKey

LOGGER = logging.getLogger(__name__)
API_VERSION = "2023-11-15"
MGMT_SCOPE = "https://management.azure.com/.default"
COSMOS_SQL_SCOPE = "https://cosmos.azure.com/.default"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subscription-id", default=os.getenv("AZURE_SUBSCRIPTION_ID"), help="Azure subscription id")
    parser.add_argument("--resource-group", required=True, help="Resource group that hosts the Cosmos account")
    parser.add_argument("--account-name", required=True, help="Cosmos account name (without .documents.azure.com)")
    parser.add_argument("--endpoint", required=True, help="Cosmos SQL endpoint, e.g. https://<account>.documents.azure.com:443/")
    parser.add_argument("--database", default="rag_agent", help="SQL database id")
    parser.add_argument("--graph-database", default="graph", help="Gremlin database id")
    parser.add_argument("--sql-container", required=True, help="SQL container to create (e.g. tenant-id-documents)")
    parser.add_argument("--graph", required=True, help="Gremlin graph/collection to create (e.g. tenant-id-graph)")
    parser.add_argument("--throughput", type=int, default=400, help="SQL throughput (RU/s)")
    parser.add_argument("--graph-throughput", type=int, default=400, help="Gremlin throughput (RU/s)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    return parser.parse_args()


def ensure_sql_container(endpoint: str, database_id: str, container_id: str, throughput: int, credential: DefaultAzureCredential) -> None:
    LOGGER.info("Ensuring SQL container %s in database %s", container_id, database_id)
    client = CosmosClient(endpoint, credential=credential, consistency_level="Session")
    database = client.create_database_if_not_exists(id=database_id, throughput=throughput)
    partition_key = PartitionKey(path="/tenantId")
    database.create_container_if_not_exists(id=container_id, partition_key=partition_key, throughput=throughput)
    LOGGER.info("SQL container %s ready", container_id)


def ensure_gremlin_graph(subscription_id: str, resource_group: str, account_name: str, database_id: str, graph_id: str, throughput: int, credential: DefaultAzureCredential) -> None:
    if not subscription_id:
        raise ValueError("Subscription id is required for Gremlin graph provisioning")

    base_id = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.DocumentDB/databaseAccounts/{account_name}"
    request_url = f"https://management.azure.com{base_id}/gremlinDatabases/{database_id}/graphs/{graph_id}?api-version={API_VERSION}"

    token = credential.get_token(MGMT_SCOPE).token
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "properties": {
            "resource": {
                "id": graph_id,
                "indexingPolicy": {
                    "automatic": True,
                    "indexingMode": "consistent"
                },
                "partitionKey": {
                    "paths": ["/tenantId"],
                    "kind": "Hash"
                }
            },
            "options": {
                "throughput": throughput
            }
        }
    }

    LOGGER.info("Ensuring Gremlin graph %s in database %s", graph_id, database_id)
    with httpx.Client(timeout=30) as client:
        response = client.put(request_url, headers=headers, json=payload)
        if response.status_code == 409:
            LOGGER.info("Graph %s already exists", graph_id)
            return
        if response.status_code in (200, 201):
            LOGGER.info("Graph %s created", graph_id)
            return
        if response.status_code == 202:
            poll_url = response.headers.get("Azure-AsyncOperation") or response.headers.get("Location")
            if not poll_url:
                response.raise_for_status()
            wait_for_completion(client, poll_url, headers)
            LOGGER.info("Graph %s created", graph_id)
            return
        response.raise_for_status()


def wait_for_completion(client: httpx.Client, poll_url: str, headers: dict, interval: int = 5, timeout: int = 300) -> None:
    elapsed = 0
    while elapsed < timeout:
        poll_response = client.get(poll_url, headers=headers)
        poll_response.raise_for_status()
        body = poll_response.json()
        status = (body.get("status") or body.get("provisioningState") or "").lower()
        if status in {"succeeded", "success"}:
            return
        if status in {"failed", "canceled"}:
            raise RuntimeError(f"Gremlin graph provisioning failed: {body}")
        time.sleep(interval)
        elapsed += interval
    raise TimeoutError("Timed out waiting for Gremlin graph provisioning")


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    credential = DefaultAzureCredential()

    ensure_sql_container(
        endpoint=args.endpoint,
        database_id=args.database,
        container_id=args.sql_container,
        throughput=args.throughput,
        credential=credential,
    )
    ensure_gremlin_graph(
        subscription_id=args.subscription_id,
        resource_group=args.resource_group,
        account_name=args.account_name,
        database_id=args.graph_database,
        graph_id=args.graph,
        throughput=args.graph_throughput,
        credential=credential,
    )
    LOGGER.info("Cosmos resources ready")


if __name__ == "__main__":
    main()
