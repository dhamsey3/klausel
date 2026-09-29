"""Ask a question against the local index; the answer comes from local Ollama.

Questions can be German or English; the answer and CLI output follow the question's
language unless --lang is given.

klausel-query "Welche Kündigungsfristen gelten?"
klausel-query "What notice periods apply?"
klausel-query --source contracts/dienstleistungsvertrag.txt "Is the liability clause valid?"
klausel-query            # interactive mode
"""

from __future__ import annotations

import argparse
import sys

from klausel.lang import SUPPORTED, Lang, detect_language
from klausel.llm import OllamaClient, OllamaError
from klausel.rag import answer

_UI: dict[Lang, dict[str, str]] = {
    "de": {"context": "Kontext", "sources": "Quellen", "section": "Abschnitt"},
    "en": {"context": "Context", "sources": "Sources", "section": "section"},
}


def _ask(
    question: str,
    llm: OllamaClient,
    top_k: int | None,
    source: str | None,
    show_ctx: bool,
    lang: Lang | None,
) -> None:
    lang = lang or detect_language(question)
    ui = _UI[lang]
    ctx, stream = answer(question, top_k=top_k, source=source, llm=llm, lang=lang)
    if show_ctx:
        print(f"\n--- {ui['context']} ---", file=sys.stderr)
        for i, h in enumerate(ctx.hits, 1):
            print(
                f"[{i}] {h.score:.3f} {h.source}#{h.chunk_index}: {h.text[:160]!r}", file=sys.stderr
            )
        print("---------------\n", file=sys.stderr)
    for token in stream:
        print(token, end="", flush=True)
    print()
    if ctx.hits:
        print(f"\n{ui['sources']}:")
        for i, h in enumerate(ctx.hits, 1):
            print(f"  [{i}] {h.source} ({ui['section']} {h.chunk_index}, score {h.score:.3f})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Private, local RAG over your legal documents.")
    ap.add_argument("question", nargs="*", help="omit for interactive mode")
    ap.add_argument("--top-k", type=int, default=None)
    ap.add_argument("--source", default=None, help="restrict to one document (S3 key)")
    ap.add_argument("--model", default=None, help="override OLLAMA_MODEL")
    ap.add_argument("--show-context", action="store_true")
    ap.add_argument(
        "--lang",
        choices=SUPPORTED,
        default=None,
        help="answer language (default: same as the question)",
    )
    a = ap.parse_args()

    llm = OllamaClient(model=a.model)
    try:
        llm.ensure_model()
    except OllamaError as e:
        sys.exit(str(e))

    if a.question:
        _ask(" ".join(a.question), llm, a.top_k, a.source, a.show_context, a.lang)
        return
    print(
        f"Lokaler Vertragsassistent / local contract assistant ({llm.model}). "
        "Leere Eingabe beendet / empty input quits."
    )
    while True:
        try:
            q = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            break
        _ask(q, llm, a.top_k, a.source, a.show_context, a.lang)


if __name__ == "__main__":
    main()
