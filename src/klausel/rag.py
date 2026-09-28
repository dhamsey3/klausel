"""Retrieval-augmented answering over the local vector store."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from klausel.config import get_settings
from klausel.embeddings import get_embedder
from klausel.llm import OllamaClient
from klausel.vectorstore import SearchHit, make_client, search

SYSTEM_PROMPT = """Du bist ein sorgfältiger juristischer Assistent für deutsches Vertrags- und Datenschutzrecht.
Regeln:
- Antworte ausschließlich auf Grundlage der bereitgestellten KONTEXT-Auszüge.
- Zitiere jede Aussage mit der Quellnummer in eckigen Klammern, z. B. [1].
- Wenn der Kontext die Frage nicht beantwortet, sage das ausdrücklich; erfinde nichts.
- Weise auf potenziell unwirksame oder risikoreiche Klauseln hin (z. B. nach §§ 305 ff. BGB, DSGVO).
- Antworte in der Sprache der Frage.
- Dies ist keine Rechtsberatung."""


@dataclass
class RetrievedContext:
    hits: list[SearchHit]

    def render(self) -> str:
        return "\n\n".join(
            f"[{i}] Quelle: {h.source} (Abschnitt {h.chunk_index})\n{h.text}"
            for i, h in enumerate(self.hits, start=1)
        )


def retrieve(
    question: str, top_k: int | None = None, source: str | None = None
) -> RetrievedContext:
    s = get_settings()
    vec = get_embedder().embed_query(question).tolist()
    hits = search(make_client(s), s.qdrant_collection, vec, top_k or s.retrieval_top_k, source)
    return RetrievedContext(hits=hits)


def build_messages(question: str, ctx: RetrievedContext) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"KONTEXT:\n{ctx.render()}\n\nFRAGE:\n{question}"},
    ]


def answer(
    question: str,
    *,
    top_k: int | None = None,
    source: str | None = None,
    stream: bool = True,
    llm: OllamaClient | None = None,
) -> tuple[RetrievedContext, Iterator[str]]:
    ctx = retrieve(question, top_k, source)
    llm = llm or OllamaClient()
    if not ctx.hits:
        return ctx, iter(["Keine relevanten Dokumente im lokalen Index gefunden."])
    return ctx, llm.chat(build_messages(question, ctx), stream=stream)
