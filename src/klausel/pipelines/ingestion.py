"""ZenML ingestion pipeline: MinIO -> extract -> redact -> chunk -> embed -> Qdrant.

Run:
    python -m klausel.pipelines.ingestion            # or: klausel-ingest
    klausel-ingest --prefix contracts/ --no-cache

Note on privacy: ZenML persists every step output in its local artifact store
(`zenml artifact-store list`). Redaction therefore happens inside the *first*
step, so no unredacted text is ever written there.
"""

# No `from __future__ import annotations`: ZenML resolves step type hints at runtime.
import argparse
import logging
from typing import Annotated, Any

from zenml import get_step_context, log_metadata, pipeline, step

from klausel.config import get_settings
from klausel.embeddings import get_embedder
from klausel.ingest.chunking import chunk_text
from klausel.ingest.extract import SUPPORTED_SUFFIXES, extract_text
from klausel.ingest.redact import redact
from klausel.storage import get_object_bytes, list_objects, make_s3_client
from klausel.vectorstore import (
    delete_stale_chunks,
    ensure_collection,
    make_client,
    upsert_chunks,
)

logger = logging.getLogger(__name__)

Document = dict[str, Any]  # {source, etag, text, redactions}
ChunkRecord = dict[str, Any]  # payload stored in Qdrant (+ "text")


@step(enable_cache=False)  # bucket contents change between runs
def load_documents(
    bucket: str, prefix: str, redact_pii: bool
) -> Annotated[list[Document], "documents"]:
    """List supported objects in MinIO, extract text, pseudonymise PII."""
    s3 = make_s3_client()
    docs: list[Document] = []
    skipped: list[str] = []
    total_redactions = 0
    for obj in list_objects(s3, bucket, prefix, SUPPORTED_SUFFIXES):
        try:
            text = extract_text(obj.key, get_object_bytes(s3, bucket, obj.key))
        except Exception as e:  # noqa: BLE001 - one corrupt file must not kill the run
            logger.warning("Skipping %s: %s", obj.key, e)
            skipped.append(obj.key)
            continue
        if not text:
            skipped.append(obj.key)
            continue
        counts: dict[str, int] = {}
        if redact_pii:
            r = redact(text)
            text, counts = r.text, dict(r.counts)
            total_redactions += sum(counts.values())
        docs.append({"source": obj.key, "etag": obj.etag, "text": text, "redactions": counts})

    if not docs:
        raise RuntimeError(f"No readable documents under s3://{bucket}/{prefix}")
    log_metadata(
        metadata={"documents": len(docs), "skipped": skipped, "pii_redactions": total_redactions},
        infer_artifact=True,
    )
    logger.info(
        "Loaded %d documents (%d skipped, %d PII redactions)",
        len(docs),
        len(skipped),
        total_redactions,
    )
    return docs


@step
def chunk_documents(
    documents: list[Document], chunk_size: int, chunk_overlap: int
) -> Annotated[list[ChunkRecord], "chunks"]:
    run_name = get_step_context().pipeline_run.name
    chunks: list[ChunkRecord] = []
    for doc in documents:
        pieces = chunk_text(doc["text"], chunk_size, chunk_overlap)
        for c in pieces:
            chunks.append(
                {
                    "source": doc["source"],
                    "etag": doc["etag"],
                    "chunk_index": c.index,
                    "chunk_count": len(pieces),
                    "char_start": c.start,
                    "text": c.text,
                    "language": "de",
                    "pii_redacted": bool(doc["redactions"]),
                    "ingest_run": run_name,
                }
            )
    log_metadata(metadata={"chunks": len(chunks)}, infer_artifact=True)
    return chunks


@step
def embed_chunks(chunks: list[ChunkRecord]) -> Annotated[list[list[float]], "embeddings"]:
    embedder = get_embedder()
    logger.info("Embedding %d chunks on %s", len(chunks), embedder.device)
    vectors = embedder.embed_passages([c["text"] for c in chunks])
    log_metadata(
        metadata={"dimension": embedder.dimension, "device": embedder.device},
        infer_artifact=True,
    )
    return vectors.tolist()


@step
def upsert_to_qdrant(
    chunks: list[ChunkRecord], embeddings: list[list[float]], collection: str
) -> Annotated[int, "upserted_points"]:
    if not embeddings:
        return 0
    client = make_client()
    ensure_collection(client, collection, dim=len(embeddings[0]))
    n = upsert_chunks(client, collection, embeddings, chunks)

    # Remove leftover chunks from earlier, longer versions of the same document.
    for source, count in {c["source"]: c["chunk_count"] for c in chunks}.items():
        delete_stale_chunks(client, collection, source, keep=count)

    log_metadata(metadata={"collection": collection, "points": n})
    return n


@pipeline(name="legal_docs_ingestion")
def ingestion_pipeline(
    bucket: str,
    prefix: str = "",
    collection: str = "legal_docs_de",
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
    redact_pii: bool = True,
) -> None:
    docs = load_documents(bucket=bucket, prefix=prefix, redact_pii=redact_pii)
    chunks = chunk_documents(docs, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    vectors = embed_chunks(chunks)
    upsert_to_qdrant(chunks, vectors, collection=collection)


def main() -> None:
    s = get_settings()
    ap = argparse.ArgumentParser(description="Ingest documents from MinIO into Qdrant.")
    ap.add_argument("--bucket", default=s.s3_bucket)
    ap.add_argument("--prefix", default=s.s3_prefix)
    ap.add_argument("--collection", default=s.qdrant_collection)
    ap.add_argument("--chunk-size", type=int, default=s.chunk_size)
    ap.add_argument("--chunk-overlap", type=int, default=s.chunk_overlap)
    ap.add_argument("--no-redact", action="store_true", help="disable PII pseudonymisation")
    ap.add_argument("--no-cache", action="store_true", help="force every step to re-run")
    a = ap.parse_args()

    ingestion_pipeline.with_options(enable_cache=not a.no_cache)(
        bucket=a.bucket,
        prefix=a.prefix,
        collection=a.collection,
        chunk_size=a.chunk_size,
        chunk_overlap=a.chunk_overlap,
        redact_pii=s.redact_pii and not a.no_redact,
    )


if __name__ == "__main__":
    main()
