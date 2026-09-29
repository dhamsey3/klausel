# Klausel

**Self-hosted, GDPR-compliant document AI & contract reviewer for German legal text,
usable in German or English.**

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
| LLM | [Ollama](https://ollama.com) (`qwen2.5:3b` by default) | Local answer generation with cited sources |

## Status

Early prototype. Unit tests (chunking, PII redaction, language handling) pass
with `make test`, no services needed. Deployed end to end on a Hyper-V Ubuntu VM
(MinIO, Qdrant, Ollama) with the app on a Windows PC; see
[All services on a VM](#all-services-on-a-vm-app-on-your-pc-hyper-v-example).
Not hardened for production and not evaluated on real client data.

## Repository layout

```
klausel/
├── docker-compose.yml        # MinIO (+ bucket init), Qdrant, optional Ollama
├── docker-compose.vm.yml     # overlay for a shared VM: Qdrant requires an API key
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
│   ├── rag.py                # retrieval + German/English legal system prompts
│   ├── lang.py               # German/English detection for questions and documents
│   ├── ingest/
│   │   ├── extract.py        # txt/md/pdf/docx -> normalised text
│   │   ├── redact.py         # rule-based PII pseudonymisation
│   │   └── chunking.py       # § / Art. / paragraph / sentence-aware chunker
│   ├── pipelines/
│   │   └── ingestion.py      # ZenML steps + pipeline  (klausel-ingest)
│   ├── cli/
│   │   └── query.py          # RAG CLI                (klausel-query)
│   └── web/
│       ├── app.py            # local web UI server    (klausel-web)
│       └── index.html        # single-page UI, no external assets
├── scripts/
│   ├── download_model.py     # the ONLY online step: fetch embedding model to ./models
│   ├── seed_minio.py         # upload local files into the bucket
│   ├── erase_document.py     # GDPR Art. 17: delete a document everywhere
│   └── vm/                   # VM setup: Docker (+ Compose v2), CPU-only Ollama
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
ollama pull qwen2.5:3b               # or qwen2.5:7b for better answers; set OLLAMA_MODEL in .env
make seed                            # upload data/samples/ to MinIO
make ingest                          # run the ZenML pipeline
make ask Q="Welche Klauseln in dem Dienstleistungsvertrag sind problematisch?"
make ask Q="Which clauses in the service contract are problematic?"
```

MinIO stopped publishing community Docker images in late 2025, so
`docker/minio/Dockerfile` builds pinned releases of the server and `mc` client
from the public AGPL source. The first `make infra` therefore compiles Go and
takes a few minutes; later starts reuse the built images.

- MinIO console: <http://localhost:9001> (user/password from `.env`)
- Qdrant dashboard: <http://localhost:6333/dashboard>
- ZenML runs: `zenml pipeline runs list`, or `zenml login --local` for the local dashboard

## Web UI

```bash
make web            # or: klausel-web  (Windows: .venv\Scripts\klausel-web)
```

Then open <http://127.0.0.1:8000>. Ask in German or English, watch the answer stream
in, click a citation such as `[1]` to jump to the exact clause text, restrict the
search to one document, and drop PDF/DOCX/TXT/MD files to upload and index them (they
go to `uploads/` in the bucket, then through the normal ZenML pipeline). The page's
own labels switch between EN and DE.

It is a **single-user tool for the machine it runs on**: it binds to `127.0.0.1`
only, requires an `X-Klausel` header on every API call (so other websites can't post
to it from your browser) and rejects non-local `Host` headers (DNS rebinding). There
is no login; don't expose it on a network as is.

## Running Klausel on your own PC

The repository contains no documents, keys or model weights, so anyone can clone it
and run their own private instance. Each installation has its **own** documents and
index; nothing is shared with other installations.

You need: Git, Python 3.11/3.12, [Docker Desktop](https://www.docker.com/products/docker-desktop/)
(for MinIO + Qdrant) and [Ollama](https://ollama.com/download).

**Windows (PowerShell):**

```powershell
git clone https://github.com/dhamsey3/klausel.git; cd klausel
copy .env.example .env      # then set MINIO_ROOT_PASSWORD and AWS_SECRET_ACCESS_KEY
                            # to the same long random value
docker compose up -d        # MinIO + Qdrant on 127.0.0.1 (first run builds MinIO)
py -3.12 -m venv .venv
.venv\Scripts\pip install -e ".[web]"
.venv\Scripts\zenml init
.venv\Scripts\python scripts\download_model.py   # one-time, ~470 MB
ollama pull qwen2.5:3b      # or qwen2.5:7b with a GPU / 16 GB+ RAM
.venv\Scripts\klausel-web                         # http://127.0.0.1:8000
```

**macOS / Linux:** `cp .env.example .env`, then `make infra install model`,
`ollama pull qwen2.5:3b` and `make web`.

If PyTorch fails to load on Windows (`c10.dll`), install the Microsoft Visual C++
Redistributable: `winget install Microsoft.VCRedist.2015+.x64`.

To use **one shared set of documents** instead, run the services on a server that
everyone can reach (see the VM section below, with an External switch rather than the
Default Switch), give each user the same `.env`, and add authentication and TLS in
front of the services first.

## German and English

Ask in either language: the answer, the source labels and the CLI output follow the
language of the question (override with `klausel-query --lang en|de`). English answers
quote the key German contract wording with a translation. Retrieval is cross-lingual
(multilingual-e5), so English questions find German clauses and vice versa. Documents
may be German or English; each chunk stores its detected `language`, and the chunker
also splits English contracts at "Section / Clause / Article N".

**Model choice:** `qwen2.5:3b` runs on a CPU-only VM but is slow there (minutes per
answer) and its legal reasoning is unreliable: in testing it called a clause valid
that excludes liability for intent, which is void under § 276 Abs. 3 BGB. Use
`qwen2.5:7b` or larger on a GPU for anything beyond a demo.

## Running MinIO on a VM (e.g. on a Windows workstation)

The Python code only needs `AWS_ENDPOINT_URL` to point at MinIO, so moving
MinIO off your laptop is a config change:

1. **On the VM**, copy `docker-compose.yml`, `docker/` and `.env`, set `BIND_ADDR` to the
   VM's private IP, set a strong `MINIO_ROOT_PASSWORD` (MinIO refuses to start on a
   non-loopback address with the default one) and start only MinIO:
   ```bash
   docker compose up -d minio minio-init
   ```
2. **Make the VM reachable from your dev machine.**
   - Hyper-V / VirtualBox / VMware in **bridged** mode: the VM has its own LAN IP; use that.
   - **NAT** mode: add port forwards 9000 and 9001 from the Windows host to the VM,
     then use the Windows host's IP.
   - Allow inbound TCP 9000/9001 in **Windows Defender Firewall** (and the VM's
     firewall, e.g. `ufw allow from <your-laptop-ip> to any port 9000,9001`).
3. **On your dev machine**, in `.env` (`AWS_SECRET_ACCESS_KEY` must equal the VM's
   `MINIO_ROOT_PASSWORD`):
   ```
   AWS_ENDPOINT_URL=http://<vm-or-host-ip>:9000
   AWS_SECRET_ACCESS_KEY=<same as MINIO_ROOT_PASSWORD on the VM>
   ```
   Qdrant and Ollama can stay local (`make infra` still starts Qdrant; leaving MinIO
   running locally too is harmless).

### All services on a VM, app on your PC (Hyper-V example)

Use this when the dev machine has no Docker or the services should live on one box:
MinIO, Qdrant and Ollama run on an Ubuntu VM; the Python app (ingestion + queries)
runs on your PC. This is the tested setup: Ubuntu 22.04 VM on the Hyper-V Default
Switch, Windows 11 host.

**VM size:** 4 vCPUs, 8+ GB RAM, **25 GB+ disk**. The MinIO build needs ~3 GB of
temporary space (freed with `docker builder prune -af`), `qwen2.5:3b` needs 1.9 GB.

1. **Copy files to the VM** (`~/klausel`): `docker-compose.yml`,
   `docker-compose.vm.yml`, `docker/`, `scripts/vm/` and your `.env`
   (`chmod 600 .env`).
2. **Install Docker** (Ubuntu packages + Compose v2, Docker networks moved off
   `172.17.x.x`, firewall), then log out and back in:
   ```bash
   sudo scripts/vm/install-docker.sh
   ```
3. **Start MinIO and Qdrant.** The overlay makes Qdrant require `QDRANT_API_KEY`:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.vm.yml up -d --build
   docker builder prune -af   # reclaim the MinIO build cache
   ```
4. **Install Ollama, CPU-only, without sudo.** Skips the GPU libraries (~60 MB
   instead of the 3.75 GB Docker image) and runs as a systemd user service:
   ```bash
   scripts/vm/install-ollama-cpu.sh 0.34.4 qwen2.5:3b
   ```
5. **On your PC**, the same `.env` with the VM's address:
   ```
   AWS_ENDPOINT_URL=http://<vm-hostname>.mshome.net:9000
   QDRANT_URL=http://<vm-hostname>.mshome.net:6333
   OLLAMA_URL=http://<vm-hostname>.mshome.net:11434
   ```
   `MINIO_ROOT_PASSWORD` = `AWS_SECRET_ACCESS_KEY` and `QDRANT_API_KEY` must be long
   random values; generate them with
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

**Hyper-V Default Switch notes**

- It is NAT-ed: only the host (and other VMs) can reach the VM, not your LAN. For
  access from other computers, use an External switch.
- The VM's IP, and even the subnet, **change when the host reboots**. Use
  `<vm-hostname>.mshome.net` on the PC and `BIND_ADDR=0.0.0.0` on the VM, so Docker
  never tries to bind a vanished IP.
- The switch uses `172.16.0.0/12` addresses, which collide with Docker's default
  `172.17.0.0/16`; `scripts/vm/install-docker.sh` moves Docker to `10.200.x.x`.
- **Growing the disk:** Hyper-V creates an *automatic checkpoint* when the VM starts,
  and a disk with checkpoints cannot be expanded. In an admin PowerShell:
  ```powershell
  $vm = 'Ubuntu 22.04 LTS'
  Get-VMSnapshot -VMName $vm | Remove-VMSnapshot          # merges into the main disk
  while ((Get-VMHardDiskDrive -VMName $vm).Path -like '*.avhdx') { Start-Sleep 2 }
  Resize-VHD -Path (Get-VMHardDiskDrive -VMName $vm).Path -SizeBytes 25GB
  Set-VM -Name $vm -AutomaticCheckpointsEnabled $false
  ```
  then inside the VM:
  `echo 1 | sudo tee /sys/class/block/sda/device/rescan && sudo growpart /dev/sda 1 && sudo resize2fs /dev/sda1`.

**Admin consoles** (from the PC; for asking questions use the [Web UI](#web-ui)):

| What | URL | Login |
|---|---|---|
| MinIO console (browse/upload/delete documents) | `http://<vm-hostname>.mshome.net:9001` | `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` |
| Qdrant dashboard (inspect the index) | `http://<vm-hostname>.mshome.net:6333/dashboard` | `QDRANT_API_KEY` |
| ZenML dashboard (ingestion runs) | `zenml login --local` | local |

**Performance (CPU-only VM, 4 vCPUs):** ingesting the sample contract takes ~15 s;
an answer from `qwen2.5:3b` takes ~1 minute when the VM is idle and several minutes
when it is busy. Ollama on a GPU is much faster.

Plain HTTP is fine on a private LAN. If traffic crosses networks you don't
control, put MinIO behind TLS (MinIO reads certs from `~/.minio/certs`) and use `https://`.

## GDPR / EU AI Act design notes

| Concern | How Klausel handles it |
|---|---|
| No third-country transfers (Art. 44 ff. GDPR) | All services local; HF offline mode forced in code; ZenML analytics, Qdrant telemetry and MinIO update checks disabled; ports bind to loopback by default. |
| Data minimisation / privacy by design (Art. 5(1)(c), 25) | E-mail, IBAN, phone, tax ID, SV number and birth dates are pseudonymised **in the first pipeline step**, before anything is embedded or persisted as a ZenML artifact. |
| Right to erasure (Art. 17) | Deterministic point IDs + `source` payload index; `scripts/erase_document.py <key>` removes vectors and all MinIO object versions. Each ingest run also prunes vectors of documents deleted from the bucket. |
| Accountability (Art. 5(2)) | ZenML records every run with its parameters and metadata (doc counts, redaction counts, model, device); MinIO bucket versioning keeps an audit trail. |
| Transparency (AI Act Art. 50) | Answers cite numbered sources; the prompt forbids answering outside the retrieved context and states it is not legal advice. |

This is an engineering blueprint, not legal advice. Do a DPIA (Art. 35)
before processing real client data.

## Development

```bash
make test     # unit tests (no Docker needed)
make lint
```

On Windows without `make`, run the targets directly (Python 3.12 via the `py` launcher):

```powershell
py -3.12 -m venv .venv; .venv\Scripts\pip install -e ".[dev]"; .venv\Scripts\zenml init
.venv\Scripts\python scripts\download_model.py
.venv\Scripts\python scripts\seed_minio.py
.venv\Scripts\klausel-ingest
.venv\Scripts\klausel-query --show-context "Welche Kündigungsfristen gelten?"
.venv\Scripts\pytest -q
```

## Next steps

- NER-based redaction of names and addresses (e.g. a local spaCy `de_core_news_lg` model).
- Clause-level review mode: extract clauses, then check each against BGB §§ 305–310 and Art. 28 GDPR.
- Hybrid search (BM25 + dense) via Qdrant sparse vectors for exact § references.
- Replace the MinIO root credentials with a dedicated read-only access key for the pipeline.
- Evaluate larger models (`qwen2.5:7b`+) on a GPU; the 3B default misjudges legal validity.
