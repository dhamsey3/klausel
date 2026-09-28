"""Qdrant access: collection setup, idempotent upserts, search and erasure."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from klausel.config import Settings, get_settings

# Fixed namespace so point IDs are deterministic across runs.
_POINT_NS = uuid.UUID("6f1c1c3e-5d0a-4b9e-9f0e-3a7c2d1b8e44")


@dataclass(frozen=True)
class SearchHit:
    score: float
    text: str
    source: str
    chunk_index: int
    payload: dict[str, Any]


def point_id(source_key: str, chunk_index: int) -> str:
    """Same document + chunk -> same ID, so re-ingesting overwrites instead of duplicating."""
    return str(uuid.uuid5(_POINT_NS, f"{source_key}#{chunk_index}"))


def make_client(settings: Settings | None = None) -> QdrantClient:
    s = settings or get_settings()
    return QdrantClient(url=s.qdrant_url, api_key=s.qdrant_api_key or None, timeout=60)


def ensure_collection(client: QdrantClient, name: str, dim: int) -> None:
    if client.collection_exists(name):
        existing = client.get_collection(name).config.params.vectors
        size = existing.size if isinstance(existing, qm.VectorParams) else None
        if size is not None and size != dim:
            raise ValueError(
                f"Collection '{name}' has dim={size} but the embedder produces dim={dim}. "
                "Use a new QDRANT_COLLECTION or drop the old one."
            )
        return
    client.create_collection(
        collection_name=name,
        vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
    )
    # Payload index lets us delete/filter by source document quickly.
    client.create_payload_index(
        name, field_name="source", field_schema=qm.PayloadSchemaType.KEYWORD
    )


def upsert_chunks(
    client: QdrantClient,
    collection: str,
    vectors: list[list[float]],
    payloads: list[dict[str, Any]],
    batch_size: int = 256,
) -> int:
    points = [
        qm.PointStruct(id=point_id(p["source"], p["chunk_index"]), vector=v, payload=p)
        for v, p in zip(vectors, payloads, strict=True)
    ]
    for i in range(0, len(points), batch_size):
        client.upsert(collection_name=collection, points=points[i : i + batch_size], wait=True)
    return len(points)


def delete_stale_chunks(client: QdrantClient, collection: str, source: str, keep: int) -> None:
    """Drop chunks beyond `keep` for a document that got shorter on re-ingest."""
    client.delete(
        collection_name=collection,
        points_selector=qm.FilterSelector(
            filter=qm.Filter(
                must=[
                    qm.FieldCondition(key="source", match=qm.MatchValue(value=source)),
                    qm.FieldCondition(key="chunk_index", range=qm.Range(gte=keep)),
                ]
            )
        ),
        wait=True,
    )


def erase_source(client: QdrantClient, collection: str, source: str) -> None:
    """Right to erasure (GDPR Art. 17): remove every vector derived from a document."""
    client.delete(
        collection_name=collection,
        points_selector=qm.FilterSelector(
            filter=qm.Filter(
                must=[qm.FieldCondition(key="source", match=qm.MatchValue(value=source))]
            )
        ),
        wait=True,
    )


def search(
    client: QdrantClient,
    collection: str,
    query_vector: list[float],
    top_k: int = 5,
    source: str | None = None,
) -> list[SearchHit]:
    flt = (
        qm.Filter(must=[qm.FieldCondition(key="source", match=qm.MatchValue(value=source))])
        if source
        else None
    )
    res = client.query_points(
        collection_name=collection,
        query=query_vector,
        limit=top_k,
        query_filter=flt,
        with_payload=True,
    )
    return [
        SearchHit(
            score=pt.score,
            text=pt.payload.get("text", ""),
            source=pt.payload.get("source", "?"),
            chunk_index=int(pt.payload.get("chunk_index", -1)),
            payload=pt.payload,
        )
        for pt in res.points
    ]
