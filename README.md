# Klausel

**Self-hosted, GDPR-compliant document AI & contract reviewer for German legal text.**

Every component runs on hardware you control. There are no runtime calls to
OpenAI, AWS, the Hugging Face Hub or any other cloud API; the only network
access is a one-time model download that you run deliberately (and can do on
a different machine).

```
            ┌──────────────┐   ZenML pipeline (local orchestrator)
 .pdf/.docx │   MinIO      │   ┌──────────┬──────────┬──────────┬──────────┐
 .txt/.md ─►│ (S3, :9000)  │──►│ extract  │ redact   │ chunk    │ embed    │──► Qdrant (:6333)
            └──────────────┘   │ text     │ PII      │ §-aware  │ e5-small │      │
                               └──────────┴──────────┴──────────┴──────────┘      │
                                                                                  ▼
 question ──► embed (local) ──► top-k search ──► prompt + context ──► Ollama (:11434) ──► answer + sources
```

## Stack

| Layer | Tool | Role |
|---|---|---|
| Object storage | [MinIO](https://github.com/minio/minio) (built from source) | S3-compatible store for raw documents, versioned bucket |
| Orchestration | [ZenML](https://zenml.io) (local orchestrator) | Ingestion pipeline with tracked runs and metadata |
| Embeddings | [`intfloat/multilingual-e5-small`](https://huggingface.co/intfloat/multilingual-e5-small) | Multilingual (German-capable) sentence embeddings, loaded from disk |
| Vector database | [Qdrant](https://qdrant.tech) | Similarity search, idempotent upserts, per-document erasure |
| LLM | [Ollama](https://ollama.com) (`mistral:7b-instruct` by default) | Local answer generation with cited sources |

## Status

Early prototype. Unit tests for chunking and PII redaction pass (`make test`,
no services needed). Not hardened for production and not evaluated on real
client data.

## Repository layout

```
klausel/
├── docker-compose.yml        # MinIO (+ bucket init), Qdrant, optional Ollama
├── .env.example              # single source of truth for all settings
├── pyproject.toml            # package + CLI entry points
├── Makefile                  # common commands
├── src/klausel/
│   ├── __init__.py           # forces HF / ZenML offline mode on import
│   ├── config.py             # pydantic-settings, reads .env
│   ├── storage.py            # boto3 client for MinIO
│   ├── embeddings.py         # local SentenceTransformer (local_files_only)
│   ├── vectorstore.py        # Qdrant: collection, idempotent upsert, search, erasure
│   ├── llm.py                # tiny Ollama HTTP client (streaming)
│   ├── rag.py                # retrieval + German legal system prompt
│   ├── ingest/
│   │   ├── extract.py        # txt/md/pdf/docx -> normalised text
│   │   ├── redact.py         # rule-based PII pseudonymisation
│   │   └── chunking.py       # § / Art. / paragraph / sentence-aware chunker
│   ├── pipelines/
│   │   └── ingestion.py      # ZenML steps + pipeline  (klausel-ingest)
│   └── cli/
│       └── query.py          # RAG CLI                (klausel-query)
├── scripts/
│   ├── download_model.py     # the ONLY online step: fetch embedding model to ./models
│   ├── seed_minio.py         # upload local files into the bucket
│   └── erase_document.py     # GDPR Art. 17: delete a document everywhere
├── data/samples/             # fictional German contract for testing
├── models/                   # local model weights (git-ignored)
└── tests/                    # unit tests (no services needed)
```

## Quick start (everything on one machine)

Requirements: Docker, Python **3.11 or 3.12** (ZenML/PyTorch wheels lag behind
newer Pythons), and [Ollama](https://ollama.com) installed natively (on Apple
Silicon the native app uses the Metal GPU; Ollama in Docker on macOS is CPU-only).

```bash
cp .env.example .env                 # change MINIO_ROOT_PASSWORD + AWS_SECRET_ACCESS_KEY together
make infra                           # MinIO + bucket + Qdrant
make install                         # venv + deps (uses uv if present)
make model                           # one-time download of intfloat/multilingual-e5-small
ollama pull mistral:7b-instruct      # or llama3.1:8b; set OLLAMA_MODEL in .env
make seed                            # upload data/samples/ to MinIO
make ingest                          # run the ZenML pipeline
make ask Q="Welche Klauseln in dem Dienstleistungsvertrag sind problematisch?"
```

MinIO stopped publishing community Docker images in late 2025, so
`docker/minio/Dockerfile` builds pinned releases of the server and `mc` client
from the public AGPL source. The first `make infra` therefore compiles Go and
takes a few minutes; later starts reuse the built images.

- MinIO console: <http://localhost:9001> (user/password from `.env`)
- Qdrant dashboard: <http://localhost:6333/dashboard>
- ZenML runs: `zenml pipeline runs list`, or `zenml login --local` for the local dashboard

## Running MinIO on a VM (e.g. on a Windows workstation)

The Python code only needs `AWS_ENDPOINT_URL` to point at MinIO, so moving
MinIO off your laptop is a config change:

1. **On the VM**, copy `docker-compose.yml` + `.env`, set `BIND_ADDR` to the
   VM's private IP and start only MinIO:
   ```bash
   docker compose up -d minio minio-init
   ```
2. **Make the VM reachable from your dev machine.**
   - Hyper-V / VirtualBox / VMware in **bridged** mode: the VM has its own LAN IP; use that.
   - **NAT** mode: add port forwards 9000 and 9001 from the Windows host to the VM,
     then use the Windows host's IP.
   - Allow inbound TCP 9000/9001 in **Windows Defender Firewall** (and the VM's
     firewall, e.g. `ufw allow from <your-laptop-ip> to any port 9000,9001`).
3. **On your dev machine**, in `.env`:
   ```
   AWS_ENDPOINT_URL=http://<vm-or-host-ip>:9000
   ```
   Qdrant and Ollama can stay local (`make infra` still starts Qdrant; leaving MinIO
   running locally too is harmless).

Plain HTTP is fine on a private LAN. If traffic crosses networks you don't
control, put MinIO behind TLS (MinIO reads certs from `~/.minio/certs`) and use `https://`.

## GDPR / EU AI Act design notes

| Concern | How Klausel handles it |
|---|---|
| No third-country transfers (Art. 44 ff. GDPR) | All services local; HF offline mode forced in code; ZenML analytics, Qdrant telemetry and MinIO update checks disabled; ports bind to loopback by default. |
| Data minimisation / privacy by design (Art. 5(1)(c), 25) | E-mail, IBAN, phone, tax ID, SV number and birth dates are pseudonymised **in the first pipeline step**, before anything is embedded or persisted as a ZenML artifact. |
| Right to erasure (Art. 17) | Deterministic point IDs + `source` payload index; `scripts/erase_document.py <key>` removes vectors and all MinIO object versions. |
| Accountability (Art. 5(2)) | ZenML records every run with its parameters and metadata (doc counts, redaction counts, model, device); MinIO bucket versioning keeps an audit trail. |
| Transparency (AI Act Art. 50) | Answers cite numbered sources; the prompt forbids answering outside the retrieved context and states it is not legal advice. |

This is an engineering blueprint, not legal advice. Do a DPIA (Art. 35)
before processing real client data.

## Development

```bash
make test     # unit tests (no Docker needed)
make lint
```

## Next steps

- NER-based redaction of names and addresses (e.g. a local spaCy `de_core_news_lg` model).
- Clause-level review mode: extract clauses, then check each against BGB §§ 305–310 and Art. 28 GDPR.
- Hybrid search (BM25 + dense) via Qdrant sparse vectors for exact § references.
- Replace the MinIO root credentials with a dedicated read-only access key for the pipeline.
