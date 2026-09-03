# Sermon QA Bot

An intelligent **Sermon Question-Answering Bot** integrated on **Telegram** or **WhatsApp** and powered by **Retrieval-Augmented Generation (RAG)**. Users ask questions about past sermons and receive precise, context-grounded answers citing the source date and the speaker.

## How It Works

```
[User Question] ──► [Embedding API] ──► [Vector Search (sqlite-vec)]
                                              │
                                              ▼
                                     [Top-5 Relevant Chunks]
                                              │
                                              ▼
                                     [Gen-AI] ──► [Formatted Answer]
                                              │
                                              ▼
                                   [Telegram / WhatsApp]
```

Sermon notes are stored in a markdown file (`2026-Sermons.md`). A parser extracts each sermon section (date, speaker, topic, scriptures, notes), embeds them via OpenAI, and indexes them in SQLite with `sqlite-vec` for vector similarity search. When a user asks a question, the bot retrieves the most relevant sermon chunks and uses Gen-AI to generate a grounded answer.

## Features

- **Question Answering** — Ask about sermon content and get answers with citations
- **Scripture Lookup** — Find sermons where specific verses were referenced
- **Speaker Filtering** — Query within a specific speaker's sermons
- **Date-Range Queries** — Search sermons within a given date range
- **Topic Discovery** — Find what was taught on a particular topic
- **Incremental Updates** — Auto-detects new sermons appended to the markdown file via `watchdog`

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI + Uvicorn |
| LLM | Maybe OpenAI GPT-4o-mini |
| Embeddings | Maybe OpenAI text-embedding-3-small (1536-dim) |
| Vector Search | sqlite-vec |
| Database | SQLite (single file, zero-infrastructure) |
| Telegram Bot | python-telegram-bot |
| WhatsApp | Twilio |
| File Watcher | watchdog (inotify) |
| Containerization | Docker + Docker Compose |

## Project Structure

```
├── src/
│   ├── app/
│   │   ├── main.py             # FastAPI app factory, lifespan events
│   │   ├── config.py           # Pydantic settings (env vars)
│   │   ├── routers/
│   │   │   ├── telegram.py     # POST /webhook/telegram
│   │   │   ├── whatsapp.py     # POST /webhook/whatsapp
│   │   │   └── query.py        # POST /query (REST test endpoint)
│   │   ├── services/
│   │   │   ├── parser.py       # Custom SermonMarkdownParser
│   │   │   ├── embeddings.py   # EmbeddingService
│   │   │   ├── retriever.py    # Vector search queries
│   │   │   └── generator.py    # AnswerGenerator (Gen-AI)
│   │   ├── db/
│   │   │   ├── database.py     # SQLite connection, init_db()
│   │   │   └── models.py       # Table definitions / Pydantic models
│   │   └── schemas/
│   │       └── sermon.py       # Pydantic models
│   └── data/
│       ├── sermons.db          # SQLite database
│       └── 2026-Sermons.md     # Source sermon notes
├── watcher.py                  # watchdog FileChangeHandler
├── seed.py                     # One-time: parse + embed all sermons
├── .env                        # API keys, tokens (gitignored)
├── .env.example
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/webhook/telegram` | Receive Telegram updates |
| `POST` | `/webhook/whatsapp` | Receive WhatsApp messages |
| `POST` | `/query` | Direct REST query |
| `GET` | `/health` | Health check / readiness probe |
| `GET` | `/docs` | Auto-generated Swagger UI |

## Quick Start

1. **Clone the repo** and copy the environment template:
   ```bash
   cp .env.example .env
   ```

2. **Add your API keys** to `.env`:
   - `OPENAI_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` (for WhatsApp)

3. **Seed the database** with existing sermons:
   ```bash
   python seed.py
   ```

4. **Run with Docker Compose** (recommended):
   ```bash
   docker compose up -d
   ```
   Or directly with Uvicorn:
   ```bash
   uvicorn src.app.main:app --reload
   ```

5. **Set the Telegram webhook**:
   ```bash
   curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=https://<domain>/webhook/telegram&secret_token=<SECRET>"
   ```

## Deployment

The app can be deployed via Docker on any VPS or PaaS:

```yaml
# docker-compose.yml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./.env:/app/.env
    restart: unless-stopped
```

A reverse proxy (Caddy or nginx) will handle TLS termination.

## Architecture

See [2026-Sermons-Architecture.md](./docs/2026-Sermons-Architecture.md) for the full architecture document covering data pipeline, query flow, SQLite schema, file watcher strategy, and messaging platform setup. See [CHANGELOG.md](./docs/CHANGELOG.md) for what has been built so far.
