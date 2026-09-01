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