"""Ask a question against the local index; the answer comes from local Ollama.

klausel-query "Welche Kündigungsfristen gelten?"
klausel-query --source contracts/dienstleistungsvertrag.txt "Ist die Haftungsklausel wirksam?"
klausel-query            # interactive mode
"""

from __future__ import annotations

import argparse
import sys

from klausel.llm import OllamaClient, OllamaError
from klausel.rag import answer


def _ask(
    question: str, llm: OllamaClient, top_k: int | None, source: str | None, show_ctx: bool
) -> None:
    ctx, stream = answer(question, top_k=top_k, source=source, llm=llm)
    if show_ctx:
        print("\n--- Kontext ---", file=sys.stderr)
        for i, h in enumerate(ctx.hits, 1):
            print(
                f"[{i}] {h.score:.3f} {h.source}#{h.chunk_index}: {h.text[:160]!r}", file=sys.stderr
            )
        print("---------------\n", file=sys.stderr)
    for token in stream:
        print(token, end="", flush=True)
    print()
    if ctx.hits:
        print("\nQuellen:")
        for i, h in enumerate(ctx.hits, 1):
            print(f"  [{i}] {h.source} (Abschnitt {h.chunk_index}, Score {h.score:.3f})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Private, local RAG over your legal documents.")
    ap.add_argument("question", nargs="*", help="omit for interactive mode")
    ap.add_argument("--top-k", type=int, default=None)
    ap.add_argument("--source", default=None, help="restrict to one document (S3 key)")
    ap.add_argument("--model", default=None, help="override OLLAMA_MODEL")
    ap.add_argument("--show-context", action="store_true")
    a = ap.parse_args()

    llm = OllamaClient(model=a.model)
    try:
        llm.ensure_model()
    except OllamaError as e:
        sys.exit(str(e))

    if a.question:
        _ask(" ".join(a.question), llm, a.top_k, a.source, a.show_context)
        return
    print(f"Lokaler Vertragsassistent ({llm.model}). Leere Eingabe beendet.")
    while True:
        try:
            q = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            break
        _ask(q, llm, a.top_k, a.source, a.show_context)


if __name__ == "__main__":
    main()
