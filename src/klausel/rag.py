"""Retrieval-augmented answering over the local vector store (German or English)."""

from __future__ import annotations

import re
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
- Gib wieder, was die Klauseln sagen. Beurteile Wirksamkeit oder Risiken nur, wenn die Frage
  danach fragt; formuliere dann einen Prüfpunkt für eine Anwältin/einen Anwalt, kein Ergebnis.
- Beantworte nur die gestellte Frage; prüfe nicht ungefragt den ganzen Vertrag.
- Antworte auf Deutsch, auch wenn Auszüge englisch sind.
- Dies ist keine Rechtsberatung.""",
    "en": """You are a careful legal assistant for German contract and data-protection law.
Rules:
- Answer only on the basis of the CONTEXT excerpts provided.
- Cite every statement with its source number in square brackets, e.g. [1]. Use only
  source numbers that appear in the CONTEXT.
- Name statutory sections only when you are sure of them; never invent provisions.
- If the context does not answer the question, say so explicitly; do not make anything up.
- Report what the clauses say. Assess validity or risk only when the question asks for it,
  and then frame it as a point for a lawyer to check, not as a conclusion.
- Answer only the question asked; do not review the whole contract unprompted.
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


# Questions about the tool itself are answered without retrieval or the model: a small
# model told to answer "only from the contract" otherwise invents a contract review.
_META_RE = re.compile(
    r"^\s*(?:what (?:can|do) you do|what are you|who are you|how do(?:es)? (?:this|you|it) work"
    r"|what is this|help|hilfe|was kannst du|was bist du|wer bist du|wie funktionierst du"
    r"|wie funktioniert (?:das|dies))\b",
    re.IGNORECASE,
)

CAPABILITIES: dict[Lang, str] = {
    "en": """I answer questions about the contracts indexed here, in English or German, and cite the exact clauses I used as [1], [2], … so you can check them.

For example:
- "What notice period applies to termination?"
- "Who is liable for damages, and is liability limited?"
- "May the provider use subcontractors outside the EU?"

Tips: pick a single document in the menu to keep answers focused, and click a citation to read the clause. You can add PDF, DOCX, TXT or MD files below.

Limits: I run on a small local model. I can misread clauses or get the law wrong, so treat my answers as a starting point, check the cited text, and don't rely on them as legal advice. Nothing you ask or upload leaves your own machines.""",
    "de": """Ich beantworte Fragen zu den hier indexierten Verträgen, auf Deutsch oder Englisch, und zitiere die verwendeten Klauseln als [1], [2], … zur Kontrolle.

Zum Beispiel:
- „Welche Kündigungsfrist gilt?“
- „Wer haftet bei Schäden, und ist die Haftung begrenzt?“
- „Darf der Auftragnehmer Unterauftragnehmer außerhalb der EU einsetzen?“

Tipps: Wählen Sie im Menü ein einzelnes Dokument für gezieltere Antworten, und klicken Sie auf ein Zitat, um die Klausel zu lesen. Unten können Sie PDF-, DOCX-, TXT- oder MD-Dateien hinzufügen.

Grenzen: Ich laufe auf einem kleinen lokalen Modell. Ich kann Klauseln falsch lesen oder das Recht falsch einschätzen. Nutzen Sie meine Antworten als Ausgangspunkt, prüfen Sie den zitierten Text, und verlassen Sie sich nicht darauf als Rechtsberatung. Nichts, was Sie fragen oder hochladen, verlässt Ihre eigenen Rechner.""",
}


def is_meta_question(question: str) -> bool:
    return len(question) <= 80 and bool(_META_RE.match(question))


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
    if is_meta_question(question):
        return RetrievedContext(hits=[]), iter([CAPABILITIES[lang]])
    ctx = retrieve(question, top_k, source)
    llm = llm or OllamaClient()
    if not ctx.hits:
        return ctx, iter([NO_HITS[lang]])
    return ctx, llm.chat(build_messages(question, ctx, lang), stream=stream)
