"""Retrieval-augmented answering over the local vector store (German or English)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from klausel.config import get_settings
from klausel.embeddings import get_embedder
from klausel.lang import Lang, detect_language
from klausel.llm import OllamaClient
from klausel.vectorstore import SearchHit, make_client, search

# One prompt per answer language: naming the language explicitly keeps small models
# from drifting, and documents may be in either language regardless of the question.
SYSTEM_PROMPTS: dict[Lang, str] = {
    "de": """Du bist ein sorgfältiger juristischer Assistent für deutsches Vertrags- und Datenschutzrecht.
Regeln:
- Antworte ausschließlich auf Grundlage der bereitgestellten KONTEXT-Auszüge.
- Zitiere jede Aussage mit der Quellnummer in eckigen Klammern, z. B. [1]. Verwende nur
  Quellnummern, die im KONTEXT vorkommen.
- Nenne Paragraphen nur, wenn du dir sicher bist; erfinde keine Normen.
- Wenn der Kontext die Frage nicht beantwortet, sage das ausdrücklich; erfinde nichts.
- Weise auf potenziell unwirksame oder risikoreiche Klauseln hin (z. B. nach §§ 305 ff. BGB, DSGVO).
- Antworte auf Deutsch, auch wenn Auszüge englisch sind.
- Dies ist keine Rechtsberatung.""",
    "en": """You are a careful legal assistant for German contract and data-protection law.
Rules:
- Answer only on the basis of the CONTEXT excerpts provided.
- Cite every statement with its source number in square brackets, e.g. [1]. Use only
  source numbers that appear in the CONTEXT.
- Name statutory sections only when you are sure of them; never invent provisions.
- If the context does not answer the question, say so explicitly; do not make anything up.
- Point out potentially invalid or risky clauses (e.g. under §§ 305 ff. BGB, GDPR/DSGVO).
- Answer in English. The excerpts may be in German: quote the key German wording where
  it matters and give an English translation.
- This is not legal advice.""",
}

_LABELS: dict[Lang, dict[str, str]] = {
    "de": {"context": "KONTEXT", "question": "FRAGE", "source": "Quelle", "section": "Abschnitt"},
    "en": {"context": "CONTEXT", "question": "QUESTION", "source": "Source", "section": "section"},
}

NO_HITS: dict[Lang, str] = {
    "de": "Keine relevanten Dokumente im lokalen Index gefunden.",
    "en": "No relevant documents found in the local index.",
}


@dataclass
class RetrievedContext:
    hits: list[SearchHit]

    def render(self, lang: Lang = "de") -> str:
        lb = _LABELS[lang]
        return "\n\n".join(
            f"[{i}] {lb['source']}: {h.source} ({lb['section']} {h.chunk_index})\n{h.text}"
            for i, h in enumerate(self.hits, start=1)
        )


def retrieve(
    question: str, top_k: int | None = None, source: str | None = None
) -> RetrievedContext:
    s = get_settings()
    vec = get_embedder().embed_query(question).tolist()
    hits = search(make_client(s), s.qdrant_collection, vec, top_k or s.retrieval_top_k, source)
    return RetrievedContext(hits=hits)


def build_messages(question: str, ctx: RetrievedContext, lang: Lang = "de") -> list[dict[str, str]]:
    lb = _LABELS[lang]
    return [
        {"role": "system", "content": SYSTEM_PROMPTS[lang]},
        {
            "role": "user",
            "content": f"{lb['context']}:\n{ctx.render(lang)}\n\n{lb['question']}:\n{question}",
        },
    ]


def answer(
    question: str,
    *,
    top_k: int | None = None,
    source: str | None = None,
    stream: bool = True,
    llm: OllamaClient | None = None,
    lang: Lang | None = None,
) -> tuple[RetrievedContext, Iterator[str]]:
    """`lang=None` answers in the language the question is written in."""
    lang = lang or detect_language(question)
    ctx = retrieve(question, top_k, source)
    llm = llm or OllamaClient()
    if not ctx.hits:
        return ctx, iter([NO_HITS[lang]])
    return ctx, llm.chat(build_messages(question, ctx, lang), stream=stream)
