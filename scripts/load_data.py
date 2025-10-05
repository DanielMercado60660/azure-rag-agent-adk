#!/usr/bin/env python3
"""Load content into Azure AI Search and Cosmos DB for a tenant."""

import argparse
import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, Iterable, List

from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from openai import AzureOpenAI

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True, help="Tenant identifier used for partitioning")
    parser.add_argument("--documents", required=True, help="Path to a file or directory of documents (txt, md, json, jsonl)")
    parser.add_argument("--search-endpoint", required=True, help="Azure AI Search endpoint")
    parser.add_argument("--search-index", required=True, help="Azure AI Search index name")
    parser.add_argument("--cosmos-endpoint", required=True, help="Cosmos SQL endpoint")
    parser.add_argument("--cosmos-database", default="rag_agent", help="Cosmos database id")
    parser.add_argument("--cosmos-container", required=True, help="Cosmos container id")
    parser.add_argument("--aoai-endpoint", required=True, help="Azure OpenAI endpoint")
    parser.add_argument("--aoai-deployment", required=True, help="Embedding deployment name")
    parser.add_argument("--aoai-api-version", default="2024-02-15-preview", help="Azure OpenAI API version")
    parser.add_argument("--batch-size", type=int, default=16, help="Search upload batch size")
    parser.add_argument("--dry-run", action="store_true", help="Parse documents but do not write to services")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    return parser.parse_args()


def iter_documents(path: Path) -> Iterable[Dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)

    if path.is_file():
        yield from parse_file(path)
    else:
        for file_path in sorted(path.rglob("*")):
            if file_path.is_file():
                yield from parse_file(file_path)


def parse_file(path: Path) -> Iterable[Dict[str, str]]:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".markdown"}:
        text = path.read_text(encoding="utf-8")
        yield {
            "id": hash_id(path),
            "content": text,
            "source": str(path.name),
        }
    elif suffix == ".jsonl":
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            yield normalize_payload(payload, path)
    elif suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            for item in payload:
                yield normalize_payload(item, path)
        else:
            yield normalize_payload(payload, path)
    else:
        LOGGER.debug("Skipping unsupported file %s", path)


def normalize_payload(payload: Dict[str, str], path: Path) -> Dict[str, str]:
    if "content" not in payload:
        raise ValueError(f"Document {path} missing 'content' field")
    doc_id = payload.get("id") or hash_id(path, payload.get("title") or payload["content"][:64])
    normalized = {
        "id": str(doc_id),
        "content": payload["content"],
        "source": payload.get("source") or path.name,
        "metadata": payload.get("metadata") or {},
    }
    title = payload.get("title")
    if title:
        normalized["metadata"]["title"] = title
    return normalized


def hash_id(path: Path, extra: str = "") -> str:
    digest = hashlib.md5((str(path) + extra).encode("utf-8")).hexdigest()
    return digest


def embed_documents(docs: List[Dict[str, str]], client: AzureOpenAI, deployment: str) -> List[List[float]]:
    embeddings = []
    for doc in docs:
        response = client.embeddings.create(model=deployment, input=doc["content"])
        embeddings.append(response.data[0].embedding)
    return embeddings


def upload_search(tenant_id: str, docs: List[Dict[str, str]], embeddings: List[List[float]], client: SearchClient) -> None:
    payload = []
    for doc, vector in zip(docs, embeddings):
        payload.append({
            "id": doc["id"],
            "content": doc["content"],
            "content_vector": vector,
            "metadata": json.dumps(doc.get("metadata", {})),
            "tenant_id": tenant_id,
            "source": doc.get("source"),
        })
    if payload:
        result = client.upload_documents(documents=payload)
        failed = [r for r in result if not r.succeeded]
        if failed:
            raise RuntimeError(f"Failed to upload {len(failed)} documents to search: {failed}")
        LOGGER.info("Uploaded %s documents to Azure AI Search", len(payload))


def upsert_cosmos(tenant_id: str, docs: List[Dict[str, str]], client: CosmosClient, database_id: str, container_id: str) -> None:
    database = client.get_database_client(database_id)
    container = database.get_container_client(container_id)
    try:
        container.read()
    except CosmosResourceNotFoundError as exc:
        raise RuntimeError(
            f"Cosmos container '{container_id}' not found in database '{database_id}'. Run setup_cosmos.py first."
        ) from exc
    for doc in docs:
        item = {
            "id": doc["id"],
            "tenantId": tenant_id,
            "source": doc.get("source"),
            "content": doc["content"],
            "metadata": doc.get("metadata", {}),
        }
        container.upsert_item(item)
    LOGGER.info("Upserted %s documents into Cosmos", len(docs))


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    docs = list(iter_documents(Path(args.documents)))
    if not docs:
        LOGGER.warning("No documents found at %s", args.documents)
        return

    LOGGER.info("Loaded %s documents from disk", len(docs))

    if args.dry_run:
        for doc in docs[:3]:
            LOGGER.debug("Sample doc: %s", doc["id"])
        LOGGER.info("Dry run enabled; skipping uploads")
        return

    credential = DefaultAzureCredential()

    aoai_client = AzureOpenAI(
        azure_endpoint=args.aoai_endpoint,
        api_version=args.aoai_api_version,
        azure_ad_token_provider=lambda: credential.get_token("https://cognitiveservices.azure.com/.default").token,
    )

    search_client = SearchClient(endpoint=args.search_endpoint, index_name=args.search_index, credential=credential)
    cosmos_client = CosmosClient(url=args.cosmos_endpoint, credential=credential)

    batched = [docs[i: i + args.batch_size] for i in range(0, len(docs), args.batch_size)]
    for batch in batched:
        vectors = embed_documents(batch, aoai_client, args.aoai_deployment)
        upload_search(args.tenant_id, batch, vectors, search_client)
        upsert_cosmos(args.tenant_id, batch, cosmos_client, args.cosmos_database, args.cosmos_container)

    LOGGER.info("Data load completed for tenant %s", args.tenant_id)


if __name__ == "__main__":
    main()
