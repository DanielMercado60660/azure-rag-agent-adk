#!/usr/bin/env python3
"""Provision an Azure AI Search index tailored for the RAG agent."""

import argparse
import logging
from typing import Optional

from azure.identity import DefaultAzureCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswVectorSearchAlgorithmConfiguration,
    PrioritizedFields,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchableField,
    SemanticConfiguration,
    SemanticField,
    SemanticSettings,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
    VectorSearchAlgorithmKind,
)

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True, help="Azure AI Search endpoint, e.g. https://<name>.search.windows.net")
    parser.add_argument("--index-name", required=True, help="Name of the index to create (e.g. tenant-kb)")
    parser.add_argument("--dimensions", type=int, default=1536, help="Embedding dimensions. Defaults to 1536")
    parser.add_argument("--semantic-config", default="rag-semantic", help="Semantic configuration name")
    parser.add_argument("--vector-profile", default="rag-profile", help="Vector search profile name")
    parser.add_argument("--force", action="store_true", help="Delete and recreate the index if it already exists")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    return parser.parse_args()


def ensure_index(client: SearchIndexClient, index_name: str, dimensions: int, semantic_config: str, vector_profile: str, force: bool = False) -> None:
    if force:
        try:
            client.delete_index(index_name)
            LOGGER.info("Deleted existing index %s", index_name)
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.debug("Nothing to delete for %s: %s", index_name, exc)

    try:
        existing = client.get_index(index_name)
        if existing and not force:
            LOGGER.info("Index %s already exists; skipping creation", index_name)
            return
    except Exception:
        LOGGER.debug("Index %s not found; will create", index_name)

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=False, sortable=False),
        SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="en.lucene", searchable=True, retrievable=True),
        SearchField(name="content_vector", type=SearchFieldDataType.Collection(SearchFieldDataType.Single), searchable=True, filterable=False, sortable=False, vector_search_dimensions=dimensions, vector_search_profile_name=vector_profile),
        SearchField(name="metadata", type=SearchFieldDataType.String, facetable=False, filterable=False, sortable=False, retrievable=True, searchable=True, analyzer_name="standard.lucene"),
        SimpleField(name="tenant_id", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SimpleField(name="source", type=SearchFieldDataType.String, filterable=True, sortable=True, facetable=True),
        SimpleField(name="created_at", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswVectorSearchAlgorithmConfiguration(
                name="hnsw-default",
                kind=VectorSearchAlgorithmKind.HNSW,
                parameters={
                    "m": 16,
                    "efConstruction": 400,
                    "metric": "cosine"
                },
            )
        ],
        profiles=[
            VectorSearchProfile(
                name=vector_profile,
                algorithm_configuration_name="hnsw-default"
            )
        ],
    )

    semantic_settings = SemanticSettings(configurations=[
        SemanticConfiguration(
            name=semantic_config,
            prioritized_fields=PrioritizedFields(
                title_field=SemanticField(field_name="metadata"),
                content_fields=[SemanticField(field_name="content")]
            )
        )
    ])

    index = SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=vector_search,
        semantic_settings=semantic_settings,
    )

    client.create_index(index)
    LOGGER.info("Created index %s", index_name)


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    credential = DefaultAzureCredential()
    client = SearchIndexClient(endpoint=args.endpoint, credential=credential)
    ensure_index(
        client=client,
        index_name=args.index_name,
        dimensions=args.dimensions,
        semantic_config=args.semantic_config,
        vector_profile=args.vector_profile,
        force=args.force,
    )


if __name__ == "__main__":
    main()
