# Changelog

## Scope 1 — Foundations (1 Sept 2026)

What this round built:

- Set up the project skeleton: folder layout, environment, and how the
  project is installed and run.
- Built a reader that understands the church's sermon-note style and turns
  each entry into searchable pieces, capturing the date, speaker, topic,
  and Bible references.
- Added support for Word documents (.docx) and PDF files, alongside the
  sermon notes, so their content can also be searched later.
- Set up the storage database where all this content is kept, with a
  design that keeps sermons and other documents in one place.
- Made the whole pipeline safe to re-run ie repeating it never creates
  duplicates.
- Prepared the groundwork for the question-answering engine coming next.

Nothing user-facing yet... this is the foundation the chatbot will sit on.

## Scope 2 — The Question-Answering Bot (2 Sept 2026)

What this round built:

- Wired real embeddings (OpenAI) and a real answering model (DeepSeek), so
  the bot can now actually answer questions about the sermons.
- Added a search step that finds the most relevant sermon passages for a
  question, and an answer step that writes a response grounded in those
  passages with metadata.
- Built a web backend with a couple of endpoints: a simple one for testing
  questions directly, plus the hooks Telegram will call. WhatsApp is wired
  the same way and only needs its integration finished to go live.
- Added conversation in memory history: it keeps recent turns in memory
  and saves them so history survives a restart, and it uses the last few
  exchanges to make sense of follow-up questions.
- Added a request id to every action. If something goes wrong, logs are
  tagged so you can trace exactly what happened for that one question.
- Replaced plain error responses with friendly messages: the person asking
  sees a clear "what went wrong", and the technical details are only kept
  in the server logs.
- Prepared for Telegram by adding the bot library, and left a clean slot
  for WhatsApp/Twilio later.

## Fallbacks & timeouts (3 Sept 2026)

What this round added:

- If the main answer model (DeepSeek) or the main embedding provider (OpenAI)
  fails or takes too long, the bot now automatically falls back to free models
  via OpenRouter - so a provider outage doesn't take the bot down.
- To make the embedding fallback work, each sermon is now stored twice, once
  per model size, and the bot picks whichever provider answered.
- Every provider call has a time limit. If the whole question is taking too
  long, the user hears back right away ("this is taking longer than expected")
  instead of waiting forever.
- Adding your OpenRouter API key is now also checked on startup.

## Watcher worker (13 Sept 2026)

What this round added:

- A dedicated watcher worker that monitors the data folder for new or changed files and automatically triggers the embedding pipeline in the background.
- On startup, the worker runs a full scan in a background thread so it never blocks or delays anything.
- File changes are debounced — if a file is being saved in pieces, the worker waits for it to settle before processing.
- The watcher runs as its own service, separate from the web server, so the two can be restarted independently.

## Watcher reliability fixes (24 Sept 2026)

What this round fixed:

- The watcher no longer trips over its own database. It used to try
  reading files like `sermons.db-wal` as if they were sermons; those
  are now skipped quietly.
- Re-running the watcher on the same sermon notes no longer crashes
  with a database error. If nothing changed, it moves on. If a note
  was genuinely edited, the stored copy is updated and searched
  again — but an accidental extra space or tab on its own doesn't
  count as an edit.
- When the embedding service says "slow down" (rate limit), the bot
  now waits and retries a few times (jitter with exponential backoff) before switching to the backup provider, instead of giving up on the first try.

## Scripture verses in answers (24 Sept 2026)

What this round added:

- Answers can now quote the actual Bible verse, not just the sermon
  notes. The bot looks up every scripture the sermon mentions in a
  built-in King James Bible and shows the short phrase that matters,
  with the reference attached — no need to open a Bible to check.
- Long passages are trimmed to the phrase that answers the question
  (about a line), so replies stay short and readable.
- If a verse can't be looked up for any reason, the answer still
  works — it just gives the reference on its own instead of quoting.
- The Bible is loaded once when the server starts and shared from
  memory after that, so looking up verses adds no delay to questions.

## Showcase website (25 Sept 2026)

What this round added:

- The bot now comes with its own website, served from the same app,
  so there is still only one thing to run on your server.
- The home page explains what the bot does and shows what a real
  answer looks like, with dates, speakers, and a quoted verse.
- A step-by-step setup page takes you from a fresh copy to your
  first answer, with commands you can copy and paste.
- A self-hosting page walks through putting it on a VPS two ways:
  the easy Docker route or plain Python, plus connecting Telegram
  and checking everything is healthy.
- The changelog page on the site reads this very file, so the
  website's history never falls behind the project.
