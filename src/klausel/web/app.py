"""Local web UI: ask questions (German/English), browse sources, upload documents.

    klausel-web                 # http://127.0.0.1:8000
    klausel-web --port 8080

Binds to 127.0.0.1 only: this is a single-user tool for the machine it runs on.
Browser-side protections still matter on localhost, so every API call must carry an
`X-Klausel` header (a cross-site form cannot set it) and the Host header must be local
(blocks DNS rebinding).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from klausel.config import get_settings
from klausel.ingest.extract import SUPPORTED_SUFFIXES
from klausel.lang import Lang, detect_language
from klausel.llm import OllamaClient, OllamaError
from klausel.rag import answer
from klausel.storage import make_s3_client
from klausel.vectorstore import list_sources, make_client

UPLOAD_PREFIX = "uploads/"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
_INDEX_HTML = Path(__file__).with_name("index.html")

app = FastAPI(title="Klausel", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def _local_only(request: Request, call_next):
    host = (request.headers.get("host") or "").rsplit(":", 1)[0]
    if host not in _LOCAL_HOSTS:
        return JSONResponse({"detail": "local access only"}, status_code=403)
    if request.url.path.startswith("/api/") and request.headers.get("x-klausel") != "1":
        return JSONResponse({"detail": "missing X-Klausel header"}, status_code=403)
    return await call_next(request)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _INDEX_HTML.read_text(encoding="utf-8")


@app.get("/api/status")
def status() -> dict:
    s = get_settings()
    out: dict = {"model": s.ollama_model, "ollama": "ok", "qdrant": "ok", "documents": []}
    try:
        OllamaClient().ensure_model()
    except OllamaError as e:
        out["ollama"] = str(e)
    try:
        client = make_client(s)
        if client.collection_exists(s.qdrant_collection):
            out["documents"] = sorted(list_sources(client, s.qdrant_collection))
    except Exception as e:  # noqa: BLE001 - report any connection problem to the page
        out["qdrant"] = f"not reachable: {e}"
    return out


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    lang: Lang | None = None
    source: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)


def _ndjson(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"


@app.post("/api/ask")
def ask(req: AskRequest) -> StreamingResponse:
    lang = req.lang or detect_language(req.question)

    def events() -> Iterator[str]:
        try:
            ctx, stream = answer(req.question, top_k=req.top_k, source=req.source, lang=lang)
            yield _ndjson(
                {
                    "type": "sources",
                    "lang": lang,
                    "sources": [
                        {
                            "n": i,
                            "source": h.source,
                            "chunk": h.chunk_index,
                            "score": round(h.score, 3),
                            "text": h.text,
                        }
                        for i, h in enumerate(ctx.hits, 1)
                    ],
                }
            )
            for token in stream:
                yield _ndjson({"type": "token", "text": token})
            yield _ndjson({"type": "done"})
        except Exception as e:  # noqa: BLE001 - surface the failure in the page
            yield _ndjson({"type": "error", "message": str(e)})

    return StreamingResponse(events(), media_type="application/x-ndjson")


# --- uploads -----------------------------------------------------------------


@dataclass
class _Job:
    key: str
    state: str = "running"  # running | done | failed
    log: list[str] = field(default_factory=list)


_jobs: dict[str, _Job] = {}  # insertion-ordered, so the first key is the oldest
_MAX_JOBS = 50
_ingest_lock = threading.Lock()  # one ZenML run at a time


def _safe_name(filename: str) -> str:
    name = PurePosixPath(filename.replace("\\", "/")).name
    stem, suffix = name.rsplit(".", 1) if "." in name else (name, "")
    stem = re.sub(r"[^\w\-. ]+", "_", stem).strip(" .") or "document"
    return f"{stem[:120]}.{suffix.lower()}"


def _run_ingest(job: _Job) -> None:
    # A subprocess keeps ZenML's global state and logging out of the web server.
    cmd = [sys.executable, "-m", "klausel.pipelines.ingestion", "--prefix", job.key]
    with _ingest_lock:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    lines = (proc.stdout + proc.stderr).splitlines()
    job.log = [re.sub(r"\x1b\[[0-9;]*m", "", ln) for ln in lines[-15:]]
    job.state = "done" if proc.returncode == 0 else "failed"


@app.post("/api/upload")
async def upload(file: UploadFile) -> dict:
    name = _safe_name(file.filename or "")
    if not name.endswith(SUPPORTED_SUFFIXES):
        raise HTTPException(400, f"Unsupported file type. Allowed: {', '.join(SUPPORTED_SUFFIXES)}")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File larger than 25 MB")
    if not data:
        raise HTTPException(400, "Empty file")

    s = get_settings()
    key = f"{UPLOAD_PREFIX}{name}"
    make_s3_client(s).put_object(Bucket=s.s3_bucket, Key=key, Body=data)

    job_id = uuid.uuid4().hex[:12]
    job = _jobs[job_id] = _Job(key=key)
    # Keep only recent jobs; a long-running server must not grow without bound.
    while len(_jobs) > _MAX_JOBS:
        del _jobs[next(iter(_jobs))]
    threading.Thread(target=_run_ingest, args=(job,), daemon=True).start()
    return {"job": job_id, "key": key}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job")
    return {"key": job.key, "state": job.state, "log": job.log}


def main() -> None:
    ap = argparse.ArgumentParser(description="Klausel local web UI")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()

    import uvicorn

    print(f"Klausel: http://127.0.0.1:{a.port}  (local only, Ctrl+C to stop)")
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
