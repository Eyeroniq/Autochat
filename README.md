# AutoChat

A self-hosted RAG chat assistant. Upload documents, spreadsheets or a Google Sheet and ask questions about them; answers come back with citations. The API follows the Claude Messages API, so existing clients and SDKs can talk to it unchanged, and any OpenAI-compatible model server can power it.

```text
Browser (AutoChat UI)  ─┐
API clients / SDKs      ├─►  AutoChat API  ──►  LLM API (Groq, Gemini, OpenRouter, Ollama, vLLM …)
                        │     │  retrieval, citations, tools
                        │     ├─►  Qdrant (vector store, embedded)
                        │     └─►  Embeddings server (Ollama on CPU)
```

## Features

- **Chat over your data**: PDF, Word, Excel, CSV, JSON, HTML, Markdown and SQL databases, with inline citations.
- **Google Sheets import**: paste a link to a public sheet and the tab is ingested as a CSV.
- **Guest demo mode**: visitors chat without credentials in rate-limited, read-only sessions.
- **Usage dashboard**: latency, time to first token and token usage per request, measured on the server.
- **Claude-compatible API**: `POST /v1/messages` with streaming, tools, MCP servers and token counting.
- **Low-cost deployment**: a hosted LLM API for generation, CPU-only embeddings, Docker Compose and automatic HTTPS.

## Quickstart (Docker)

Requirements: Docker with Compose, and an API key for an OpenAI-compatible LLM provider.

```bash
cp .env.lite.example .env
```

Fill in `.env`:

| Variable | Purpose |
|---|---|
| `OPENAI_API_BASE` / `OPENAI_API_KEY` | Chat model endpoint and key, e.g. `https://api.groq.com/openai/v1` |
| `AUTOCHAT_AUTH_SECRET` | Owner credential, sent as the `Authorization` header (see below) |
| `EMBEDDING_MODEL` / `AUTOCHAT_EMBED_DIM` | Embedding model run by the bundled Ollama container, and its vector size |
| `DOMAIN` | Public domain for HTTPS (optional) |

Generate the owner secret:

```bash
python -c "import base64; print('Basic ' + base64.b64encode(b'user:password').decode())"
```

Start it:

```bash
docker compose up -d --build
```

Open <http://localhost:8080/ui>. To serve it publicly over HTTPS, point `DOMAIN` at the server and run:

```bash
docker compose --profile https up -d
```

## Configuration

Settings live in `settings.yaml`; `settings-lite.yaml` is the low-compute profile used by Docker Compose (`AUTOCHAT_PROFILES=lite`). Every value can be overridden with the environment variable written next to it.

The lite profile:

- retrieves 8 chunks per question instead of 32 and caps context at 8k tokens;
- limits agent loops to 10 steps;
- turns off OCR, code execution and web tools;
- enables guest mode and usage tracking.

### Guest demo mode

With auth enabled and `AUTOCHAT_GUEST_ENABLED=true`, the UI starts a guest session for visitors without credentials.

| Setting | Default | Meaning |
|---|---|---|
| `AUTOCHAT_GUEST_MESSAGES_PER_SESSION` | 20 | Messages per guest session |
| `AUTOCHAT_GUEST_SESSION_TTL_MINUTES` | 60 | Session lifetime |
| `AUTOCHAT_GUEST_SESSIONS_PER_IP_PER_HOUR` | 5 | New sessions per client IP per hour |
| `AUTOCHAT_GUEST_DAILY_MESSAGE_LIMIT` | 300 | Messages across all guests per UTC day |
| `AUTOCHAT_GUEST_MAX_TOKENS` | 2048 | Largest output a guest can request |
| `AUTOCHAT_GUEST_TRUST_FORWARDED_FOR` | false | Read the client IP from `X-Forwarded-For` (enable behind your own reverse proxy) |

Guests can chat and read models, documents and skills. Uploads, deletions, imports and the usage dashboard need the owner secret. Guest chats cannot use code execution, web access, database connections, MCP servers or server-side URIs. Limits are kept in memory per process.

### Usage tracking

With `AUTOCHAT_USAGE_ENABLED=true`, every `POST /v1/messages` is timed and its token usage recorded in SQLite under the data folder. The **Usage** screen and `GET /v1/usage/summary?days=7` report request counts, p50/p95 latency, time to first token and token totals.

## API

Interactive docs are at `/docs` when `AUTOCHAT_SWAGGER_ENABLED=true`, and the OpenAPI spec is in [`docs/openapi.json`](docs/openapi.json).

```bash
curl http://localhost:8080/v1/messages \
  -H "Authorization: $AUTOCHAT_AUTH_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Summarise the uploaded report"}],
       "tools": [{"name": "semantic_search", "type": "semantic_search_v1"}],
       "tool_context": [{"type": "ingested_artifact", "context_filter": {"collection": "autochat_collection"}}]}'
```

| Endpoint | Purpose |
|---|---|
| `POST /v1/messages` | Chat (streaming with `"stream": true`) |
| `POST /v1/artifacts/ingest` | Ingest a file, text or URI |
| `POST /v1/artifacts/ingest/google-sheet` | Ingest one tab of a public Google Sheet |
| `GET /v1/artifacts/list` | List documents in a collection |
| `GET /v1/models` | Available models |
| `GET /v1/guest/status`, `POST /v1/guest/session` | Guest sessions |
| `GET /v1/usage/summary` | Usage dashboard data |

## Development

Requires Python 3.11 and [uv](https://docs.astral.sh/uv/). Linux or macOS (or WSL on Windows).

```bash
uv sync --extra dev --extra core
uv run autochat serve
```

Quality checks and tests:

```bash
make format lint typecheck
make test
```

Project layout:

```text
autochat/          API server (FastAPI)
  server/guest/       guest sessions, tokens and limits
  server/usage/       usage tracking middleware, store and API
  server/ingest/      ingestion, including Google Sheets
ui/                   single-file web UI (index.html) and its docs
tests/                test suite
docs/openapi.json     API specification
settings*.yaml        configuration profiles
docker-compose.yml    deployment stack
```

## License

Apache License 2.0. See [LICENSE](LICENSE).
