# AutoChat — Project Info

A guide to what AutoChat does, how it is put together, what each part of the repository is for, and everything about running it with Docker.

---

## 1. What the project does

AutoChat is a self-hosted **retrieval-augmented generation (RAG)** chat assistant with a web UI and an HTTP API.

1. You upload data: PDFs, Word, Excel, CSV, JSON, HTML, Markdown, a public Google Sheet, or a SQL database connection.
2. At **ingestion time** each document is parsed, split into chunks, turned into vectors (embeddings) and stored in a vector database (Qdrant).
3. When you ask a question, AutoChat **retrieves** the most similar chunks and sends only those to the language model with your question.
4. The model answers with **citations** that point back to the source chunks.

Because documents are chunked and indexed once at ingestion, a question never rescans whole documents; only a handful of chunks reach the model.

The API follows the **Claude Messages API** (`POST /v1/messages`), so existing clients and SDKs work against it. Generation can come from any **OpenAI-compatible** model server: hosted (Groq, Gemini, OpenRouter) or local (Ollama, vLLM, llama.cpp, LM Studio).

### Main features

| Feature | What it gives you |
|---|---|
| Document chat with citations | Answers grounded in your files, with source references |
| Structured data | Tabular analysis over CSV/Excel, natural-language queries over SQL databases |
| Google Sheets import | Paste a public sheet link; the tab is ingested as a CSV |
| Guest demo mode | Visitors chat without credentials in rate-limited, read-only sessions |
| Usage dashboard | Server-measured latency, time to first token and token usage per request |
| Claude-compatible API | Streaming, tools, MCP servers, token counting, async jobs |
| Low-cost deployment | Hosted LLM API + CPU-only embeddings, Docker Compose, automatic HTTPS |

### Architecture

```text
                 ┌──────────────────────────── AutoChat container ────────────────────────────┐
Browser / UI ──► │ FastAPI app                                                                  │
API clients  ──► │  ├─ auth (owner secret or guest token)                                       │
                 │  ├─ usage middleware (times /v1/messages, records tokens) ──► SQLite         │
                 │  ├─ routers: messages, artifacts (ingest/list/delete), models, guest, usage │
                 │  ├─ ingestion: readers → chunking → embeddings ──────────► Qdrant (local)    │
                 │  └─ chat engine: retrieve chunks → prompt → LLM → citations → SSE stream   │
                 └───────────────┬──────────────────────────────────────┬─────────────────────┘
                                 │ embeddings                           │ generation
                                 ▼                                      ▼
                     Ollama container (CPU)               OpenAI-compatible LLM API
                     e.g. nomic-embed-text                e.g. Groq / Gemini / OpenRouter
```

Request flow for one question:

1. The UI sends `POST /v1/messages` with the conversation, the tools to allow (for example `semantic_search`) and the collection to search.
2. The auth dependency accepts the owner secret, or a guest token if guest mode is on (guests are checked against an allowlist and message limits).
3. The chat engine runs an agent loop: the model can call retrieval tools; retrieved chunks are added to the context.
4. The answer streams back as server-sent events (SSE): `message_start`, `content_block_delta`… `message_delta` (with token usage), `message_stop`.
5. The usage middleware records latency, time to first token and tokens for the Usage screen.

---

## 2. Repository map

### Top-level files

| File | Purpose |
|---|---|
| `README.md` | Overview, quickstart, configuration and API summary |
| `PROJECT_INFO.md` | This document |
| `LICENSE` | Apache License 2.0 |
| `pyproject.toml` | Python package definition: dependencies, optional "extras" (feature groups such as `core`, `ingest`, `queue`), tool config (ruff, pytest, ty) |
| `uv.lock` | Exact, locked versions of every dependency (used by `uv sync --frozen` and the Docker build) |
| `version.txt` | App version shown in the API |
| `Makefile` | Shortcuts: `make test`, `make lint`, `make format`, `make typecheck`, `make run`, `make api-docs`, worker targets |
| `settings.yaml` | Default configuration for every option, each overridable by the environment variable written next to it |
| `settings-lite.yaml` | Low-compute, locked-down profile used for hosting (loaded with `AUTOCHAT_PROFILES=lite`) |
| `settings-test.yaml` | Profile used by the test suite (mock models, local stores) |
| `settings-mock.yaml` | Minimal mock profile used by `make api-docs` |
| `Dockerfile` | Multi-stage build of the AutoChat image (see section 3) |
| `docker-compose.yml` | Full deployment stack: AutoChat, Ollama, embedding-model download, optional Caddy HTTPS |
| `.env.lite.example` | Template for the `.env` file Docker Compose reads (API keys, secret, limits, domain) |
| `.dockerignore` | Keeps local data, virtualenvs, tests, git metadata and `.env` out of Docker builds |
| `.gitignore` | Keeps local data, caches, virtualenvs and `.env` out of git |
| `docs/openapi.json` | OpenAPI specification of the API (regenerate with `make api-docs`) |

### `autochat/` — the API server

The Python package is `autochat`, and so is the command-line tool (`autochat serve`). All environment variables use the `AUTOCHAT_` prefix.

**Entry points and wiring**

| File | Purpose |
|---|---|
| `__main__.py` | `python -m autochat` runs the CLI |
| `cli/main.py` | CLI definition (`serve`, `worker`, `run`, `help`) |
| `cli/commands/serve.py` | Starts the HTTP server (uvicorn) |
| `cli/commands/worker.py` | Starts a background worker in the mode set by `AUTOCHAT_WORKER_MODE` |
| `cli/commands/run.py` | Launches a connected app (for example Claude Code) pointed at this server |
| `launcher.py` | Builds the FastAPI app: middleware (request context, usage tracking, errors, CORS), all routers, UI hosting at `/ui` |
| `main.py` | Module-level `app` object for ASGI servers |
| `di.py` | Dependency-injection container (the `injector` library) |
| `initialize.py` | Start-up shared by the server and workers (logging, observability) |
| `eager_loading.py` | Warms heavy components at start-up so the first request is fast |
| `global_handler.py` | Converts exceptions into consistent JSON error responses |
| `docs.py` | OpenAPI title, description and schema clean-up |
| `constants.py`, `paths.py` | Project root, data folder and model cache locations |

**Configuration** — `settings/`

| File | Purpose |
|---|---|
| `settings.py` | Typed settings models (Pydantic) for every section: server, auth, guest, chat, retrieval, models, vector store, usage… |
| `settings_loader.py` | Loads `settings.yaml` plus the active profiles (`AUTOCHAT_PROFILES`) and merges them; discovers models from env vars |
| `yaml.py` | YAML loader that expands `${ENV_VAR:default}` placeholders |

**HTTP layer** — `server/` (one folder per API area; each has a router, request/response models and a service)

| Folder | Endpoints / purpose |
|---|---|
| `chat/` | `POST /v1/messages` (chat, streaming), token counting, request validation and mapping to the chat engine |
| `chat_async/` | `/v1/messages/async`: background chat jobs with status, stream, cancel and delete |
| `completion/` | `POST /v1/complete`: plain text completion |
| `ingest/` | `POST /v1/artifacts/ingest`, list, delete, async ingestion, document conversion |
| `ingest/google_sheets.py` | **AutoChat addition.** `POST /v1/artifacts/ingest/google-sheet`: validates a `docs.google.com` link, downloads the tab as CSV (rejecting private sheets), ingests it as a `.csv` |
| `content/` | `GET /v1/artifacts/content` and `/chunked-content`: stored document text |
| `embeddings/` | `POST /v1/embeddings` |
| `models/` | `GET /v1/models` |
| `files/` | `/v1/files`: files inside code-execution sessions |
| `skills/` | Upload, list and version "skills" (packaged instructions the model can load) |
| `tools/` | `/v1/tools/*`: call semantic search, tabular analysis, web search/fetch and database query directly |
| `mcp/` | MCP client: connects to the Model Context Protocol servers a chat request lists (with OAuth support) |
| `primitives/` | `POST /v1/primitives/search`: raw retrieval without the chat loop |
| `health/` | `GET /health` |
| `guest/` | **AutoChat addition.** Guest demo mode (see below) |
| `usage/` | **AutoChat addition.** Usage tracking (see below) |
| `utils/auth.py` | The `authenticated` dependency on every router: owner secret, or guest token when guest mode is on |
| `principal.py` | Request-scoped view of headers/cookies passed to tools and workers |

**AutoChat additions in detail**

| File | Purpose |
|---|---|
| `server/guest/guest_sessions.py` | Issues signed guest tokens (`autochat_guest_<id>.<expiry>.<HMAC>`), verifies them, and enforces per-session, per-IP and per-day limits in memory |
| `server/guest/guest_policy.py` | What guests may do: route allowlist, and chat-body rules (no MCP servers, URIs, SQL connections, code/web tools; capped `max_tokens`) |
| `server/guest/guest_router.py` | Public `GET /v1/guest/status` and `POST /v1/guest/session` |
| `server/usage/usage_middleware.py` | ASGI middleware around `POST /v1/messages`: measures latency and time to first token, reads token usage from the JSON body or SSE stream |
| `server/usage/usage_store.py` | SQLite storage and summary statistics (p50/p95, per day, recent requests); prunes old rows |
| `server/usage/usage_router.py` | `GET /v1/usage/summary?days=N` (owner only) |

**Core logic** — `components/` (the engine room; each folder is one subsystem)

| Folder | Purpose |
|---|---|
| `llm/` | Language-model registry and factories (OpenAI-compatible, Anthropic, Mistral, mock), tokenizers, prompt styles, reasoning budgets |
| `embedding/` | Embedding-model registry and factories |
| `model_discovery/` | Auto-detects models from `/v1/models` of Ollama, vLLM, llama.cpp, LM Studio and generic OpenAI servers |
| `engines/` | The chat engine: the agent loop that calls the model and tools, schedulers, interceptors, citation engine |
| `chat/` | Chat request processing: history handling, memory condensing, multimodal input, event and citation processing |
| `context/` | Builds the layered context (system prompt, tools, retrieved documents) sent to the model |
| `prompts/` | Prompt templates and builder |
| `memory/` | Conversation memory with token-based trimming |
| `ingest/` | Ingestion pipeline: parse files, page splitting, quality checks, chunking, metadata, progress reporting |
| `ingestion/` | Chooses whether ingestion runs in-process or on a worker |
| `readers/` | Format-specific parsers: Docling and MarkItDown (PDF, Office), a PDF inspector that picks OCR only where needed, PowerPoint, text/CSV/HTML/email, and vision models for images |
| `chunk/` | Chunk data models |
| `postprocessor/` | Post-retrieval steps: neighbour expansion, document-tree expansion |
| `vector_store/` | Qdrant vector store (embedded or server) |
| `node_store/` | Document and index stores (simple file-based or Postgres) |
| `tabular/` | Tabular analysis over CSV/Excel and natural-language → SQL generation |
| `database/` | Connections to user SQL databases for the `database_query` tool |
| `tools/` | Built-in tools (semantic search, summarize, tabular, web, code execution…), tool names and translation of Anthropic tool types |
| `toolsets/` | Groups of tools exposed together (for example filesystem toolsets) |
| `skills/` | Skills storage, repositories and services |
| `web/` | Web search providers and a headless-browser page scraper |
| `code_execution/`, `sandbox/`, `environment/`, `filesystems/` | Sandboxed code execution: sessions, mounts, path translation, workspace layout (disabled in the lite profile) |
| `multimodality/` | Image and audio input handling |
| `workflows/` | Multi-step workflows: retrieval, summarisation, history condensing |
| `streaming/` | Event streams for SSE (in-memory or Redis) |
| `broker/` | Message publishing used by streaming |
| `concurrency/` | Semaphores limiting parallel work (in-memory or Redis) |
| `cache/` | In-memory or Redis cache |
| `storage/` | Object storage (local or S3) |
| `persistence/`, `migrations/`, `sqlite/`, `postgres/` | Internal database (SQLite or Postgres) and its schema migrations |
| `text_processing/`, `markdown/` | Text clean-up rules and Markdown helpers |
| `files/`, `synthesizer/` | File type helpers and response synthesis |

**Other packages**

| Folder | Purpose |
|---|---|
| `chat/` | Public request models for the Messages API and chat extensions (citations, context filters) |
| `events/` | Event models streamed to clients (content blocks, deltas, errors), serialisation to SSE, event interceptors |
| `artifact_index/` | Per-document vector index management |
| `arq/` | Optional Redis-backed queue for running chat on separate worker processes |
| `celery/` | Optional RabbitMQ-backed queue for ingestion and tool workers |
| `worker/` | Worker entry point that starts the selected worker mode |
| `observability/` | Optional OpenTelemetry tracing and exporters |
| `context/` | Context propagation so request data follows work onto workers |
| `utils/` | Shared helpers: retries, batching, token counting, MIME detection, timing |

The lite deployment uses neither `arq` nor `celery`: everything runs in one process.

### `ui/` — the web interface

| File | Purpose |
|---|---|
| `index.html` | The entire UI in one file (HTML, CSS, JavaScript; no build step). Screens: Chat, Context (documents, databases, MCP, skills, custom tools), API Debugger, Usage, Settings, onboarding. Graphite-and-mint theme, guest-mode bootstrap, Google Sheet import |
| `README.md` | How the UI folder is organised |
| `docs/PRD.md` | Product requirements: behaviour of every screen, persisted state, API usage |
| `docs/STYLE_GUIDE.md` | Visual rules: colours, typography, components, the Usage chart |
| `docs/SOURCE_OF_TRUTH.md` | Where the API contract lives and non-obvious implementation notes |
| `references/*.png` | Design reference images used by the style guide |

The server serves this folder at `/ui`.

### `scripts/`

| File | Purpose |
|---|---|
| `ingest_folder.py` | Bulk-ingest a local folder (optionally watching for changes): `make ingest` |
| `auto_discover_models.py` | Query a model server and write a settings profile listing its models |
| `extract_openapi.py` | Export the OpenAPI spec to `docs/openapi.json`: `make api-docs` |
| `benchmark_chat_stream.py` | Measure latency the server adds on top of a streaming LLM |
| `set_version.py` | Update the version in `version.txt` and `pyproject.toml` |
| `update_claude_specs.py` | Keep the Claude-compatible API in sync with the upstream Anthropic spec and SDK version |
| `worker_entrypoint` | Shell entry point for worker containers (caps glibc memory arenas) |

### `tests/`

About 2,800 tests run with `pytest`, mirroring the package layout (`tests/server/…`, `tests/components/…`, `tests/events/…`). Fixtures in `tests/fixtures/` build a test app with mock models. Tests for the AutoChat additions:

- `tests/server/guest/`: tokens, limits, policy, and the routes end to end with auth enabled
- `tests/server/usage/`: the SQLite store, the middleware (streamed and JSON responses), and the summary endpoint
- `tests/server/ingest/test_google_sheets.py`: link parsing, download errors, and the ingestion route

Run them with `make test` (Linux, macOS or WSL).

---

## 3. Docker

### Services in `docker-compose.yml`

| Service | Image | Role | Ports | Starts |
|---|---|---|---|---|
| `autochat` | `autochat:local`, built from this repo | The API server and UI | `127.0.0.1:8080` → container `8080` (`AUTOCHAT_BIND` changes the host address) | Always; waits for `ollama-pull` to finish |
| `ollama` | `ollama/ollama:latest` | Runs the embedding model on CPU | none published (internal only) | Always; health-checked with `ollama list` every 10 s |
| `ollama-pull` | `ollama/ollama:latest` | One-shot job: downloads `EMBEDDING_MODEL` into Ollama, then exits | none | Once `ollama` is healthy |
| `caddy` | `caddy:2` | Reverse proxy with automatic HTTPS certificates for `DOMAIN` | `80`, `443` | Only with `--profile https` |

The chat model is **not** a container: it is the hosted API at `OPENAI_API_BASE`.

Containers reach each other by service name on the Compose network: AutoChat calls `http://ollama:11434/v1` for embeddings, and Caddy forwards to `autochat:8080`.

### Environment for the `autochat` service

Set by `docker-compose.yml`:

| Variable | Value | Why |
|---|---|---|
| `AUTOCHAT_PROFILES` | `lite` | Loads `settings-lite.yaml` on top of `settings.yaml` |
| `AUTOCHAT_PROJECT_ROOT`, `AUTOCHAT_SETTINGS_FOLDER` | `/home/worker/app` | Where settings files and the UI are found inside the image |
| `OPENAI_EMBEDDING_API_BASE` | `http://ollama:11434/v1` | Embeddings come from the Ollama container |
| `OPENAI_EMBEDDING_API_KEY` | `ollama` | Placeholder; Ollama does not check it |

Read from `.env` (copy `.env.lite.example`):

| Variable | Required | Meaning |
|---|---|---|
| `OPENAI_API_BASE` | yes | Chat model endpoint, e.g. `https://api.groq.com/openai/v1` |
| `OPENAI_API_KEY` | yes | Key for that endpoint |
| `AUTOCHAT_LLM_DEFAULT` | no | Default model id; otherwise the first discovered model |
| `AUTOCHAT_AUTH_SECRET` | yes | Owner credential (`Basic <base64 user:password>`); the server refuses to start without it |
| `EMBEDDING_MODEL` | no | Ollama embedding model (default `nomic-embed-text`) |
| `AUTOCHAT_EMBED_DIM` | no | Its vector size: 768 for nomic-embed-text, 384 for all-minilm, 1024 for mxbai-embed-large. Must match the model; changing it means re-ingesting |
| `AUTOCHAT_GUEST_ENABLED` | no | Guest demo mode (default `true` in the lite profile) |
| `AUTOCHAT_GUEST_MESSAGES_PER_SESSION` | no | Messages per guest session (20) |
| `AUTOCHAT_GUEST_DAILY_MESSAGE_LIMIT` | no | Guest messages per UTC day across all guests (300) |
| `AUTOCHAT_GUEST_TRUST_FORWARDED_FOR` | no | `true` behind Caddy so limits apply per visitor; `false` if port 8080 is exposed directly |
| `DOMAIN` | for HTTPS | Public domain Caddy requests a certificate for |
| `AUTOCHAT_BIND` | no | `127.0.0.1` (only Caddy/localhost can reach 8080) or `0.0.0.0` (expose directly) |

Any other `AUTOCHAT_*` variable from `settings.yaml` can also be added to `.env`, for example `AUTOCHAT_RETRIEVAL_TOP_K`, `AUTOCHAT_GUEST_SESSION_TTL_MINUTES`, `AUTOCHAT_GUEST_SESSIONS_PER_IP_PER_HOUR`, `AUTOCHAT_GUEST_MAX_TOKENS`, `AUTOCHAT_USAGE_ENABLED`, `AUTOCHAT_SWAGGER_ENABLED`.

### Volumes (persistent data)

| Volume | Mounted at | Holds |
|---|---|---|
| `autochat-data` | `/home/worker/app/local_data` | Ingested documents and their index (Qdrant), the internal database, the usage SQLite database, model caches |
| `ollama-models` | `/root/.ollama` | Downloaded embedding model |
| `caddy-data` | `/data` | HTTPS certificates |

`./settings-lite.yaml` is also mounted read-only into the AutoChat container, so profile changes need only a restart, not a rebuild.

Docker prefixes volume names with the project name, so on the host they are `autochat_autochat-data`, `autochat_ollama-models` and `autochat_caddy-data`.

### How the image is built (`Dockerfile`)

Multi-stage build on `python:3.11.10-slim-bookworm`, with `uv` for installs. The build argument `EXTRAS` (Compose passes `core`) selects which dependency groups and system packages go in.

| Stage | What it does |
|---|---|
| `base` | Python 3.11 plus the `uv` binary |
| `os-deps` | System packages chosen by `EXTRAS`. For `core`: libmagic, libxml2, poppler, LibreOffice, pandoc, ghostscript (documents); ffmpeg (audio/video); Chromium libraries (web scraping); MariaDB client and Microsoft ODBC driver (databases) |
| `dependencies` | Installs the locked Python dependencies into `/home/worker/app/.venv` with `uv sync --frozen`; removes `hf-xet` |
| `build` | Copies the application source: `autochat/` and `ui/` |
| `downloads` | Pre-downloads NLTK data, tiktoken encodings and the Playwright Chromium browser, so the container works offline |
| `final` | Starts from `os-deps`, creates a non-root `worker` user, copies the venv, source, downloads, `version.txt`, `settings.yaml` and `scripts/worker_entrypoint`, then installs the package |

Final image details:

- Runs as user `worker` in `/home/worker/app`; exposes port `8080`.
- `ENTRYPOINT ["autochat"]`, `CMD ["serve"]`: the container starts the API server.
- Sets `AUTOCHAT_HOME=/home/worker/app`, `HF_HOME` to the data folder, and cache paths for tiktoken and Playwright.
- The image is large (it bundles LibreOffice, ffmpeg, Chromium and ODBC drivers); expect the first build to take a while. A smaller image is possible with a narrower `EXTRAS` list, at the cost of those formats and tools.

### Common commands

Run these from the project folder.

| Task | Command |
|---|---|
| First start (build and run) | `docker compose up -d --build` |
| Start with HTTPS | `docker compose --profile https up -d --build` |
| Status | `docker compose ps` |
| Follow AutoChat logs | `docker compose logs -f autochat` |
| Restart after editing `.env` or `settings-lite.yaml` | `docker compose up -d` |
| Rebuild after code changes | `docker compose up -d --build autochat` |
| Stop (keep data) | `docker compose down` |
| Stop and **delete all data** | `docker compose down -v` |
| Health check | `curl http://127.0.0.1:8080/health` |
| Back up documents and usage data | `docker run --rm -v autochat_autochat-data:/data -v "$PWD":/backup alpine tar czf /backup/autochat-data.tgz -C /data .` |

The UI is at `http://localhost:8080/ui` (or `https://<DOMAIN>/ui`).

### Hosting checklist

1. A Linux server with Docker (2+ CPU cores and 4 GB+ RAM is comfortable for the embedding model and the app).
2. Point the domain's DNS `A` record at the server; open ports 80 and 443.
3. Fill in `.env`, including `DOMAIN` and `AUTOCHAT_GUEST_TRUST_FORWARDED_FOR=true`.
4. `docker compose --profile https up -d --build`.
5. Sign in as owner in **Settings** (the username and password behind `AUTOCHAT_AUTH_SECRET`), upload or import demo documents, then check the **Usage** screen after a few questions.

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| AutoChat exits at start with `AUTOCHAT_AUTH_SECRET is not set` | `.env` missing the secret |
| `autochat` waits forever | `ollama-pull` failed: check `docker compose logs ollama-pull` (network, or a wrong `EMBEDDING_MODEL` name) |
| Ingestion errors about vector size | `AUTOCHAT_EMBED_DIM` does not match the embedding model; fix it and re-ingest |
| Every guest hits the session limit at once | Behind Caddy without `AUTOCHAT_GUEST_TRUST_FORWARDED_FOR=true`, all visitors share Caddy's IP |
| Guest limits reset unexpectedly | Limits live in memory and reset when the container restarts |
| No HTTPS certificate | DNS not pointing at the server yet, or ports 80/443 blocked |

---

## 4. Configuration profiles at a glance

| Setting | Default (`settings.yaml`) | Lite profile |
|---|---|---|
| Auth | off | on, secret required |
| Guest mode | off | on |
| Usage tracking | off | on |
| Retrieved chunks per question (`top_k`) | 32 | 8 |
| Max agent iterations | 100 | 10 |
| Max context length | model limit | 8,192 tokens |
| OCR on ingestion | on | off |
| Code execution | available | off; the owner can enable it in `.env` |
| Web search, web fetch | available | off; not offered in the UI |
| API docs at `/docs` | on | off |
| Server workers | auto | 1 (required for in-memory guest limits) |
