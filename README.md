# Undiary

> The diary you don't keep. You leave a note; the filing happens to it.

Undiary is a captain's log for one person at a time. You put a thought in
a text box (dictation optional, editing encouraged), or you record a
sound, or both at once in a single entry. The entry gets a date and
disappears into a database, where a small model reads it, tags it, and
files it. Later you search your own past by word or by tag, and it
answers.

Status: design. There is no code yet; the documents are the project.
Read [CONTEXT.md](CONTEXT.md) for the language and the rules, and
[docs/adr/](docs/adr/) for the decisions and their reasons.

## The law

Two sentences govern everything here:

1. **Capture is immutable.** What you submitted (text, audio, or both)
   never changes.
2. **Organization is derived.** Tags, transcripts, summaries, themes,
   and links are computed from capture, versioned, and re-runnable.
   When models improve, the whole history gets refiled for a dime.

The practical consequence: you never re-say anything, and every future
idea about metadata is retroactive by default.

## Planned shape

- Django and Postgres on Cloud Run, hand-written HTML, CSS, and vanilla
  JavaScript in front. No build step.
- Google sign-in with an allowlist. Built for one user, shaped so it
  doesn't have to be.
- Enrichment by a small model with structured output. Watched tags
  (yours, with definitions) are checked on every entry; free tags are
  proposed; themes emerge later, corpus-wide.
- A one-way markdown mirror into a private vault, so the archive
  outlives every choice above.

## Privacy

This repository is the machinery, not the diary. Entries, tags, audio,
keys, and the mirror live elsewhere, privately. If you find a secret in
this repo, that is a bug; please say so.

## Run it

Nothing runs yet. This section will earn its heading.

## License

MIT. See [LICENSE](LICENSE).
