# Church Sermon QA Bot — Architecture Document

> **Project:** Sermon Question-Answering Bot (Telegram/WhatsApp)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Data Pipeline](#4-data-pipeline)
5. [Query Flow](#5-query-flow)
6. [API Endpoints](#6-api-endpoints)
7. [Project Structure](#7-project-structure)
8. [SQLite Schema Design](#8-sqlite-schema-design)
9. [File Change Watcher Strategy](#9-file-change-watcher-strategy)
10. [Deployment](#10-deployment)
11. [Messaging Platform Setup](#11-messaging-platform-setup)

---

## 1. System Overview

An intelligent **Sermon Question-Answering Bot** deployed on **Telegram** or **WhatsApp**, powered by **Retrieval-Augmented Generation (RAG)**. Users ask questions about past sermons and receive precise, context-grounded answers citing the source date and speaker.

### Core Capabilities

| Capability | Description |
|---|---|
| **Question Answering** | Answer questions about sermon content with citations |
| **Scripture Lookup** | Retrieve sermons where specific verses were referenced |
| **Speaker Filtering** | Answer questions limited to a specific speaker's sermons |
| **Date-Range Queries** | Query sermons within a given date range |
| **Topic Discovery** | Find what was taught on a particular topic or theme |
| **Incremental Updates** | Auto-detect new sermons appended to the markdown file |

---

## 2. High-Level Architecture

```
                          ┌──────────────────────────────────────────────────┐
                          │             2026-Sermons.md                     │
                          │       (Monitored via watchdog / inotify)        │
                          └────────────────────┬────────────────────────────┘
                                               │
                          ┌────────────────────▼────────────────────────────┐
                          │              Parser Service                     │
                          │  • Regex-based extraction per date block        │
                          │  • Fields: date, speaker, topic_type,           │
                          │    topic_title, scriptures, notes               │
                          │  • Chunking: one chunk per sermon/section       │
                          └────────────────────┬────────────────────────────┘
                                               │
                          ┌────────────────────▼────────────────────────────┐
                          │         Embedding Service                       │
                          │  • Model: OpenAI text-embedding-3-small         │
                          │  • Dimensions: 1536                             │
                          │  • Batch size: 20                               │
                          └────────────────────┬────────────────────────────┘
                                               │
                          ┌────────────────────▼────────────────────────────┐
                          │    SQLite + sqlite-vec (Single .db file)        │
                          │  • sermons table (text, metadata)               │
                          │  • sermons_embeddings virtual table (vec)       │
                          │  • verses table (scripture index)              │
                          │  • Persistence: data/sermons.db                 │
                          └────────────────────┬────────────────────────────┘
                                               │
        ┌──────────────────────────────────────┼─────────────────────────────────┐
        │                                      │                                 │
        ▼                                      ▼                                 ▼
┌──────────────────────┐          ┌───────────────────────────────┐   ┌────────────────────────┐
│    Telegram Bot      │          │     FastAPI Backend           │   │  WhatsApp (Twilio)     │
│  (python-telegram-   │◄────────►│                              │◄─►│  (webhook)              │
│   bot webhook)       │          │  /webhook/telegram           │   │                         │
│                      │          │  /webhook/whatsapp           │   │  POST /webhook/whatsapp │
│  POST /webhook/      │          │  /query        (REST)        │   │                         │
│   telegram           │          │  /health                     │   │                         │
└──────────┬───────────┘          └──────────────┬────────────────┘   └───────────┬────────────┘
           │                                     │                                │
           └──────────────────┬──────────────────┼────────────────────────────────┘
                              │                  │
                              ▼                  ▼
                  ┌──────────────────────────────────────────┐
                  │        OpenAI GPT-4o-mini                │
                  │  • Model:   gpt-4o-mini                  │
                  │  • Temp:    0.0 (deterministic)          │
                  │  • Tokens:  1024 max output              │
                  │  • System:  "Answer based ONLY on the    │
                  │              provided context. Cite      │
                  │              the sermon date and speaker.│
                  │              If unsure, say so."         │
                  └──────────────────────────────────────────┘
```

### Data Flow Summary

```
[Markdown File] ──► [Parser] ──► [Text Chunks + Metadata]
                                     │
                                     ▼
                              [Embedding API] ──► [SQLite + sqlite-vec]
                                                            ▲
[User Question] ──► [Webhook] ──► [Query Embedding] ────────┘
                                     │
                                     ▼
                              [Top-5 Chunks + Context]
                                     │
                                     ▼
                              [LLM (GPT-4o-mini)] ──► [Formatted Answer]
                                     │
                                     ▼
                          [Telegram / WhatsApp Response]
```

---

## 3. Technology Stack

### Core Framework

| Layer | Technology | Justification |
|---|---|---|
| **API Framework** | FastAPI | Async, auto-docs, Pydantic validation |
| **ASGI Server** | Uvicorn |
| **Language** | Python 3.12+ |

### AI / ML

| Component | Technology | Justification |
|---|---|---|
| **LLM** | DeepSeek `deepseek-v4-flash` | OpenAI-compatible API, cheap and fast, grounded RAG answers |
| **Embedding Model** | OpenAI text-embedding-3-small | 1536-dim, $0.02/M tokens, state-of-the-art retrieval quality |
| **Vector Search** | sqlite-vec | Zero-infrastructure, single .db file, native SQL queries |
| **Semantic Chunking** | Custom parser | Respects sermon boundaries (ie not splitting across dates) |

### Messaging

| Platform | Library | Setup Complexity |
|---|---|---|
| **Telegram** | `python-telegram-bot` (v21+) | Low — set webhook URL, no approval needed |
| **WhatsApp** | `twilio` (Python SDK) | Medium — Twilio sandbox works immediately; production needs Meta approval |

### Infrastructure

| Component | Tool |
|---|---|
| **File Watcher** | `watchdog` (inotify-based) |
| **Environment** | `python-dotenv` + `pydantic-settings` |
| **Containerization** | Docker + Docker Compose |
| **Reverse Proxy** | Caddy or nginx (for SSL termination) |
| **Process Manager** | systemd (bare metal) or Railway/Render (PaaS) |

---

## 4. Data Pipeline

### 4.1 Markdown Structure

Sermons follow a consistent structure in `2026-Sermons.md`:

```markdown
#
### 8th Feb, 2026 ###
#
#### Exhortation: Ps. Derrick - The Spirit of Excellence ####
 - The spirit of excellence sets a man above his fellows...

#### Rhema: Ps. Richard - The Need To Keep Your Spirit Sharp ####
 - Many of the crisis believers go through...
 - Pro 18:14 - The strong spirit of a man sustains him...
```

### 4.2 Parser — Extraction Schema

| Field | Type | Source | Example |
|---|---|---|---|
| `date` | `date` | `### 8th Feb, 2026 ###` | `2026-02-08` |
| `topic_type` | `str` | Heading prefix | `Exhortation`, `Rhema`, `MOE` |
| `speaker` | `str` | After colon before dash | `Ps. Derrick` |
| `topic_title` | `str` | After dash | `The Spirit of Excellence` |
| `scriptures` | `list[str]` | Regex `\w+\s?\d+:\d+(-\d+)?` | `["Daniel 3:1", "Josh 1:8"]` |
| `notes` | `str` | Bullet points under heading | Full text of the sermon notes |
| `chunk_id` | `str` | Auto-generated | `2026-02-08_exhortation_0` |

### 4.3 Chunking Strategy

```
One sermon section = One chunk

  Date Block (e.g., "8th Feb, 2026")
  ├── Exhortation chunk    (speaker, topic, notes)
  ├── Rhema chunk          (speaker, topic, notes)
  ├── MOE chunk            (speaker, topic, notes)
  └── Positive Confession chunk (speaker, topic, notes)
```

- **No cross-date splitting** — each sermon section stays intact
- **Max chunk size**: ~1000 tokens (OpenAI embedding context window = 8192, well within limits)
- **Overlap**: None needed — sermons are naturally segmented

### 4.4 Embedding & Indexing

```
text-embedding-3-small
  • Input:  "Exhortation: Ps. Derrick - The Spirit of Excellence. ..."
  • Output: [0.0023, -0.0156, ..., 0.0098]  (1536 floats)
  • Cost:   ~$0.00002 per sermon chunk
```

**Indexing procedure:**
1. Parse markdown → list of `SermonChunk` objects
2. Open SQLite connection, begin transaction
3. For each chunk: check `chunk_id` existence via `SELECT id FROM sermons WHERE id = ?`
4. For new chunks: insert into `sermons` table + insert embedding into `sermons_embeddings` virtual table
5. Commit transaction

---

## 5. Query Flow

### 5.1 Sequence Diagram

```
 User                    Bot/FastAPI               SQLite+vec            OpenAI
  │                         │                        │                    │
  │  "What did pastor       │                        │                    │
  │   Richard say about     │                        │                    │
  │   the Spirit of Might?" │                        │                    │
  │────────────────────────►│                        │                    │
  │                         │  embed question        │                    │
  │                         │───────────────────────────────────────────►│
  │                         │◄───────────────────────────────────────────│
  │                         │                        │                    │
  │                         │  query top-5           │                    │
  │                         │  (sqlite-vec cosine    │                    │
  │                         │   similarity search)   │                    │
  │                         │───────────────────────►│                    │
  │                         │◄───────────────────────│                    │
  │                         │  (5 chunks + metadata) │                    │
  │                         │                        │                    │
  │                         │  build prompt          │                    │
  │                         │───────────────────────────────────────────►│
  │                         │◄───────────────────────────────────────────│
  │                         │  (answer + sources)    │                    │
  │                         │                        │                    │
  │  "Ps. Richard taught on │                        │                    │
  │   the Spirit of Might   │                        │                    │
  │   across 3 dates:       │                        │                    │
  │   15th Feb, 22nd Feb,   │                        │                    │
  │   1st Mar..."           │                        │                    │
  │◄────────────────────────│                        │                    │
```

### 5.2 Prompt Template

```
System:
You are a helpful assistant that answers questions about church sermons.
Answer based ONLY on the provided context. Be precise and concise.
Always cite the sermon date and speaker in your answer.
If the context does not contain enough information, say so.
Do not make up or extrapolate beyond the given context.

Context:
---
Date: 2026-02-15
Speaker: Ps. Richard
Topic: The Spirit of Might 1
Scriptures: Philemon 1:4-6, Rom 4:20-21, Job 32:8, ...
Notes: Philemon 1:4-6 - Hearing of thy faith and love, ...
---
Date: 2026-02-22
Speaker: Ps. Richard
Topic: The Spirit of Might 2
...

User Question:
What did Pastor Richard say about the Spirit of Might?
```

### 5.3 Response Format

```json
{
  "answer": "Ps. Richard taught on the Spirit of Might across 3 dates:\n\n"
            "1. **15th Feb, 2026** — The Spirit of Might is one of the 7 offices "
            "of the Holy Ghost (Isa 11:1-3). He emphasized that being strengthened "
            "with might by the Spirit in the inner man (Eph 3:16) empowers us.\n\n"
            "2. **22nd Feb, 2026** — Continued that the quickness of a solution "
            "depends on your saturation with the Holy Ghost. The Spirit of Might "
            "makes you an extraordinary man walking in miracles.\n\n"
            "3. **1st Mar, 2026** — The Spirit of Might creates an Atmosphere of "
            "Miracles. Fruit-bearing is the foundation of blessings.",
  "sources": [
    {"date": "2026-02-15", "speaker": "Ps. Richard", "topic": "The Spirit of Might 1"},
    {"date": "2026-02-22", "speaker": "Ps. Richard", "topic": "The Spirit of Might 2"},
    {"date": "2026-03-01", "speaker": "Ps. Richard", "topic": "The Spirit of Might: Atmosphere of Miracles"}
  ]
}
```

---

## 6. API Endpoints

### Request lifecycle & errors

Every request is wrapped in a request scope (contextvars) with a short
`req_xxxxxxxx` id. The logging filter stamps that id on every log line so a
request's whole lifecycle can be traced even when async tasks interleave.

Errors go through `AppError(status_code, detail, error)` instead of
`HTTPException`: `detail` is human-facing and returned to the client;
`error` is developer-facing and only written to the server log alongside the
stack trace, tagged with the request id. Unexpected exceptions return a
generic 500 and are never leaked.

### Endpoints

| Method | Path | Auth | Purpose | Request Body | Response |
|---|---|---|---|---|---|
| `POST` | `/webhook/telegram` | Secret token header | Receive Telegram updates | `Update` (Telegram JSON) | `200 OK` |
| `POST` | `/webhook/whatsapp` | Twilio signature check | Receive WhatsApp messages | `Twilio.Message` form data | `<Response>` TwiML |
| `POST` | `/query` | (optional API key) | Direct REST query for testing | `{"question": "...", "k": 5}` | `{"answer": "...", "sources": [...]}` |
| `GET` | `/health` | None | Health check / readiness probe (checks DB) | — | `{"status": "ok", "db": "ok"}` or 503 `{"status": "degraded", "db": "error"}` |
| `GET` | `/docs` | None | Auto-generated Swagger UI | — | Swagger HTML |

---

## 7. Project Structure

```
Sermon/
├── README.md                        # Project overview
├── pyproject.toml                   # uv project (deps, Python 3.12+)
├── uv.lock                          # uv lockfile (committed)
├── requirements.txt                 # plain-pip fallback
├── .python-version
├── .env.example                     # Template for env vars
├── seed.py                          # Parse all sources + index (idempotent)
│
├── data/                            # Watched folder (scope 3)
│   ├── 2026-Sermons.md              # Source sermon notes
│   ├── *.docx / *.pdf               # Documents dropped in for ingestion
│   └── sermons.db                   # SQLite database (gitignored)
│
├── docs/
│   ├── 2026-Sermons-Architecture.md # This document
│   └── CHANGELOG.md                 # Updated per scope
│
└── src/
    ├── __init__.py
    ├── app/
    │   ├── __init__.py
    │   ├── config.py                # project settings
    │   │
    │   ├── schemas/
    │   │   ├── __init__.py
    │   │   └── sermon.py            # Chunk model + Source type enum
    │   │
    │   ├── db/
    │   │   ├── __init__.py
    │   │   └── database.py          # SQLite session (sync + async), init_db, sqlite-vec
    │   │
    │   └── services/
    │       ├── __init__.py
    │       ├── parser.py            # SermonMarkdownParser (custom markdown parser)
    │       ├── loaders.py           # PyPDFLoader / Docx2txtLoader + text splitter
    │       └── embeddings.py        # EmbeddingService interface + stub
    │
    └── tests/
        ├── __init__.py
        ├── test_parser.py           # Parser edge cases + full-file validation
        ├── test_loaders.py          # PDF/docx loading
        └── test_db.py               # Schema, vec0 queries (sync + async)

Planned in later scopes:
    ├── src/app/main.py                # FastAPI app factory, lifespan, request-scope middleware
    ├── src/app/routers/               # query, telegram, whatsapp endpoints
    ├── src/app/messaging/             # Messenger protocol + Telegram / WhatsApp (scaffold) impls
    ├── src/app/services/retriever.py  # sqlite-vec queries
    ├── src/app/services/generator.py  # DeepSeek answer generation
    ├── src/app/services/history.py    # ChatHistoryStore (memory + SQLite)
    ├── src/app/services/qa.py         # QA orchestration: history -> retrieve -> generate
    ├── src/app/errors.py              # AppError + exception handlers
    ├── src/app/context.py             # request context (contextvars) for async lifecycle
    ├── src/app/logging.py             # request-id logging filter
    ├── watcher.py                   # watchdog file watcher (scope 3)
    ├── Dockerfile
    └── docker-compose.yml
```

---

## 8. SQLite Schema Design

The database uses **two tables** — one for sermon text/metadata and one virtual table for vector search via sqlite-vec.

### Table: `sermons`

```sql
CREATE TABLE sermons (
    id          TEXT PRIMARY KEY,          -- e.g. "2026-02-08_exhortation_0"
    date        TEXT NOT NULL,             -- ISO format "2026-02-08"
    speaker     TEXT NOT NULL,             -- "Ps. Derrick"
    topic_type  TEXT NOT NULL,             -- "Exhortation", "Rhema", "MOE"
    topic_title TEXT,                      -- "The Spirit of Excellence"
    scriptures  TEXT,                      -- JSON array: '["Daniel 3:1", "Josh 1:8"]'
    notes       TEXT NOT NULL,             -- Full sermon notes text
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_sermons_date ON sermons(date);
CREATE INDEX idx_sermons_speaker ON sermons(speaker);
CREATE INDEX idx_sermons_topic_type ON sermons(topic_type);
```

### Virtual Table: `sermons_embeddings`

```sql
-- sqlite-vec virtual table for vector similarity search
-- 1536 dimensions = OpenAI text-embedding-3-small output size
CREATE VIRTUAL TABLE sermons_embeddings USING vec0(
    chunk_id TEXT PRIMARY KEY,             -- FK to sermons.id
    embedding FLOAT[1536] distance_metric=cosine
);
```

### Table: `chat_history`

Persists per-chat conversation turns. Recent turns are also kept in memory
(`ChatHistoryStore`), written through to this table, and the last 8 turns are
re-loaded on first touch.

```sql
CREATE TABLE chat_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    TEXT NOT NULL,    
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_chat_history_chat ON chat_history(chat_id, id);
```

### ER Diagram

```
┌──────────────────────────────────┐
│           sermons                │
├──────────────────────────────────┤
│  id              TEXT  PK        │────┐
│  date            TEXT            │    │
│  speaker         TEXT            │    │ 1:1
│  topic_type      TEXT            │    │
│  topic_title     TEXT            │    │
│  scriptures      TEXT (JSON)     │    │
│  notes           TEXT            │    │
│  created_at      TEXT            │    │
└──────────────────────────────────┘    │
                                        │
┌──────────────────────────────────┐    │
│      sermons_embeddings (vec0)   │    │
├──────────────────────────────────┤    │
│  chunk_id         TEXT  PK       │◄───┘
│  embedding        FLOAT[1536]    │
│  distance_metric  = cosine       │
└──────────────────────────────────┘
```

### Query: Similarity Search

```sql
-- Find top-5 most similar sermon chunks to a question embedding
SELECT
    s.id,
    s.date,
    s.speaker,
    s.topic_type,
    s.topic_title,
    s.scriptures,
    s.notes,
    vec.distance
FROM sermons_embeddings AS vec
JOIN sermons AS s ON s.id = vec.chunk_id
WHERE vec.embedding MATCH ?          -- ? = question_embedding
  AND vec.k = 5                      -- topk 5 results
ORDER BY vec.distance ASC;
```

### Query: Filtered Similarity Search

```sql
-- Search within a specific speaker's sermons
SELECT
    s.id,
    s.date,
    s.speaker,
    s.topic_type,
    s.topic_title,
    s.notes,
    vec.distance
FROM sermons_embeddings AS vec
JOIN sermons AS s ON s.id = vec.chunk_id
WHERE vec.embedding MATCH ?
  AND s.speaker = 'Ps. Richard'
  AND vec.k = 5
ORDER BY vec.distance ASC;
```

### Query: Date-Range + Topic Filter

```sql
-- Search within Feb-Mar 2026, only "Rhema" type
SELECT
    s.id,
    s.date,
    s.speaker,
    s.topic_type,
    s.topic_title,
    s.notes,
    vec.distance
FROM sermons_embeddings AS vec
JOIN sermons AS s ON s.id = vec.chunk_id
WHERE vec.embedding MATCH ?
  AND s.date BETWEEN '2026-02-01' AND '2026-03-31'
  AND s.topic_type = 'Rhema'
  AND vec.k = 5
ORDER BY vec.distance ASC;
```

---

## 9. File Change Watcher Strategy

### Mechanism

Use `watchdog` (cross-platform file system monitoring) to detect appends/modifications to `2026-Sermons.md`.

### Implementation

```
┌──────────────────────┐
│   watchdog Observer   │
│  (runs in background  │
│   thread)             │
└──────────┬───────────┘
           │ File modified event
           ▼
┌──────────────────────────────┐
│   on_modified()              │
│  • Re-read file              │
│  • Parse all chunks          │
│  • Get existing IDs from     │
│    SQLite: SELECT id FROM    │
│    sermons                   │
│  • Diff: find new chunks     │
│  • Embed + INSERT into       │
│    sermons + vec tables      │
└──────────────────────────────┘
```

### Algorithm

```python
existing_ids = {row[0] for row in db.execute("SELECT id FROM sermons")}
current_chunks = parser.parse_file()

for chunk in current_chunks:
    if chunk.id not in existing_ids:
        embedding = embed(chunk.text)  # 1536-dim float list
        db.execute(
            "INSERT INTO sermons (id, date, speaker, topic_type, topic_title, scriptures, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (chunk.id, chunk.date, chunk.speaker, chunk.topic_type,
             chunk.topic_title, json.dumps(chunk.scriptures), chunk.notes),
        )
        db.execute(
            "INSERT INTO sermons_embeddings (chunk_id, embedding) VALUES (?, ?)",
            (chunk.id, vec_to_blob(embedding)),  # serialize float list to blob
        )
        db.commit()
```

### Benefits
- **No full rebuild** — only new chunks are embedded
- **Idempotent** — re-running seed.py is safe
- **SQL-native** — diff uses a simple `SELECT` instead of a proprietary API
- **Transaction-safe** — all inserts wrapped in a single commit

---

## 10. Deployment

### Option A: Docker on VPS (Recommended)

```yaml
docker-compose.yml
───────────────────
services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data         
      - ./.env:/app/.env
    environment:
      - WATCH_SERMONS=true
    restart: unless-stopped
```

| Provider | Cost | Notes |
|---|---|---|
| **DigitalOcean App Platform** | ~$12/mo | Simple Git push deploy |
| **Railway** | ~$5/mo | Free credits available |
| **Hetzner VPS** | ~$4/mo + Docker | Full control, cheap |
| **Fly.io** | ~$3/mo | Global regions, generous free tier |

### Option B: Reverse Proxy Setup

```
User ──► Caddy (TLS termination) ──► FastAPI (port 8000)
         │
         ├── https://bot.example.com/webhook/telegram
         ├── https://bot.example.com/webhook/whatsapp
         └── https://bot.example.com/health
```

### SQLite Safety in Docker

- The `.db` file lives on a **named volume or bind mount** — no data loss on container restart
- SQLite **WAL mode** (`PRAGMA journal_mode=WAL`) ensures safe concurrent reads while the watcher writes
- No separate database process to manage — the `.db` file is the database

---

## 11. Messaging Platform Setup

### 11.1 Telegram

```
1. Create bot via @BotFather on Telegram
   └── Get BOT_TOKEN

2. Set webhook:
   curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=https://<domain>/webhook/telegram&secret_token=<SECRET>"

3. Bot responds to:
   • /start       — Welcome message
   • /ask <q>     — Ask a question (or just send text)
   • /help        — Usage instructions
```

### 11.2 WhatsApp (Twilio)

```
1. Sign up at twilio.com
2. Get Account SID + Auth Token
3. Activate Twilio WhatsApp Sandbox
4. Configure webhook:
   Twilio Console → WhatsApp → Sandbox → "When a message comes in"
   → POST to https://<domain>/webhook/whatsapp

Production path:
   WhatsApp Business API → Meta App Review → Go live
```

---

## Appendix A: Environment Variables

```env
# --- OpenAI ---
OPENAI_API_KEY=sk-...

# --- Telegram ---
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_SECRET_TOKEN=your-secret

# --- Twilio (WhatsApp) ---
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_NUMBER=+14155238886

# --- App ---
APP_ENV=development
LOG_LEVEL=INFO
SQLITE_DB_PATH=./data/sermons.db
SERMON_FILE_PATH=./data/2026-Sermons.md
WATCH_SERMONS=true
```

## Appendix B: Dependencies (`requirements.txt`)

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
openai>=1.30.0
sqlite-vec>=0.1.0
python-telegram-bot>=21.0
twilio>=9.0.0
watchdog>=4.0.0
python-dotenv>=1.0.0
pydantic-settings>=2.3.0
```

---