# Context: the language and the rules

This file is the domain language for Undiary. Code, docs, and
conversation use these words with exactly these meanings. When a word
drifts, fix the word or fix this file.

## The law

1. **Capture is immutable.** What arrived never changes: the submitted
   text, the uploaded audio.
2. **Organization is derived.** Everything computed from capture
   (transcripts, tags, summaries, themes, links, embeddings) is
   versioned and may be recomputed at any time. Derived data is never
   load-bearing for capture.

Corollary: adding a new extraction idea later applies to the entire
history. Re-running enrichment over a year of entries costs about a
dime, so the answer to "should this be derived?" is almost always yes.

## The words

- **Entry.** The atom. One moment's note. An entry carries text, audio,
  or both, never neither. A hummed tune with a paired note is one
  entry. **Log** is the verb.
- **Raw.** The submitted text of an entry, exactly as it arrived.
  Immutable. Dictation happens client-side (Wispr Flow or anything
  else), so raw is already human-edited by the time the server sees it.
- **Audio.** An optional recording attached to an entry. It may be
  speech, a hummed tune, or any sound worth keeping. Audio is capture
  and is kept permanently.
- **Transcript.** Derived text from an entry's audio, when the audio
  contains speech. Because audio is kept, transcripts are re-derivable
  and live on the derived side. "No speech detected" is a normal
  outcome, not an error.
- **Body.** The editable display copy of an entry, initialized from raw
  (or from the transcript when there is no raw). Fixing the
  transcriber's hearing happens here; raw and audio stay as they were.
- **Spoken at, timezone, log date.** Three fields: the UTC instant, the
  IANA timezone it happened in, and the diary day it belongs to. Log
  date is editable, because a 1 a.m. entry is usually about yesterday.
- **Enrichment.** One model pass over one entry, producing structured
  output: watched-tag verdicts, free tags, entities, a one-line
  summary. Stored whole in a versioned row. Re-runs append a new
  version; the latest wins for display.
- **Watched tag.** A per-user tag with a name and a natural-language
  definition ("project_idea: an idea for something I might build,
  however offhand"). Every enrichment pass answers yes or no for every
  active watched tag, and may store an excerpt with a hit. Adding a
  watched tag triggers retroactive re-enrichment.
- **Free tag.** An open-vocabulary tag proposed by the model. No
  taxonomy.
- **Emergent theme.** A recurring subject discovered by an occasional
  corpus-wide pass and proposed for promotion to a watched tag.
  Promotion triggers the retroactive sweep.
- **The merge rule.** Re-enrichment replaces model-sourced tags and
  never touches user-sourced ones. A user confirming or deleting a tag
  is capture, not derivation.
- **Mirror.** A one-way markdown export of entries (frontmatter of
  date, tags, and entities; body below; audio files alongside) into a
  private vault. The mirror is derived, disposable, and the plain-text
  escape hatch. It is never a write path.
- **Todo.** A derived object synthesized across entries: something the
  corpus suggests wants doing. Its existence, summary, and links are
  derived; the user's verdicts on it are capture. See
  [docs/todos.md](docs/todos.md).
- **Proposal and verdict.** The synthesis sweep proposes (a new todo,
  a color attachment, a completion); the user renders verdicts
  (accept, dismiss, done, reopen). Model proposes, user disposes; the
  merge rule, promoted a level.
- **Horizon.** How soon a todo matters: now, soon, or someday. A
  verdict, editable, never model-overwritten.
- **Seed, color, completion.** The three roles an entry can play for a
  todo: the note that started it, a note that adds detail, and the
  note that reports it done.
- **Synthesis sweep.** The corpus-level pass that reads recent entries
  and the current todo list and emits proposals. Distinct from
  per-entry enrichment; versioned and re-runnable like everything
  derived.
- **The tab law.** Notes feed todos, never the reverse. The capture
  surface stays sacred and dumb: no todo chrome on the log page, and
  entries never know todos exist.

## The schema, in outline

- `entries`: raw (nullable), audio_key (nullable), at least one
  present; body; spoken_at, tz, log_date; created_at, edited_at; a
  generated search vector over body and transcript.
- `enrichments`: entry_id, version, model, payload (JSON), created_at.
- `tags`: user_id, slug, name, kind (watched or free), definition
  (watched only), active.
- `entry_tags`: entry_id, tag_id, source (model or user), confidence.
- Later, without drama: `embeddings` (pgvector) and `links` between
  entries.

## What Undiary is not

- Not Obsidian. Obsidian is manual curation; Undiary refuses to do any
  work at capture time on principle. The mirror makes Obsidian a
  reading room over Undiary's archive, not a competitor.
- Not a taxonomy. Watched tags belong to a user. A second user brings
  their own obsessions.
