# Changelog

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