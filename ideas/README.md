# Ideas

The public backlog. Ideas about Undiary go here. Ideas about everything
else go in Undiary, once it exists.

Nothing here is a commitment. Entries leave this file by shipping or by
being wrong.

- Semantic search over embeddings (pgvector), once there is a corpus
  worth embedding.
- Links between entries, model-proposed, user-confirmed.
- The emergent-theme sweep from ADR 0004, and the promotion flow.
- Live dictation in the app itself: speak and watch the words arrive
  in the text box, with context help so the transcriber knows this
  diary's proper nouns (Crowable, not crawlable). Speech adaptation
  fed by the corpus, or a cleanup pass by the enrichment model, or
  both.
- Transcription lexicon, the nearer half of context help: pass a
  personal phrase list (project names, people) to Speech-to-Text as
  adaptation hints, so uncommon words stop arriving wrong.
- A live level indicator on the mic button: quiet when the
  microphone hears nothing, moving when it hears a voice, so a
  silent take announces itself before it is logged. (Shipped
  2026-08-29: five bars beside the mic, and a "heard nothing"
  verdict on the attach line.)
- A small splash for a newly inserted entry: a dot and a quick
  animation pushing the list down, so the log visibly receives it.
  (Shipped 2026-09-01 as the arrival flash: a bright fade and a
  settle, on new entries and on new todo proposals alike.)
- Extensibility: hooks and plugins, and notes pushed and pulled from
  other places. The API the site already speaks, made official.
- Reconsider the favicon. The log stands accused of being not
  clever.
- Service-worker background sync for the outbox, so a queued entry
  can flush even before the app is reopened. (The PWA itself shipped
  2026-08-28 in two halves: install-grade manifest, icons, worker,
  and offline page; then the offline capture queue in IndexedDB with
  in-order flush on reconnect. The captain does not check for
  signal.)
- Non-enumerable entry addresses: random slugs or ULIDs instead of
  sequential ids, so a many-user future leaks nothing about volume.
  Costs nothing to skip while the allowlist has one name on it.
- Sharing one entry on purpose: a per-entry public token, minted by
  the owner and revocable, rendering a read-only page. A deliberate
  feature, never a loosening of the owner-only rule.
- Permalinks for individual entries, so one note can be pointed at.
  (Shipped 2026-08-28: /entries/<id>, the timestamp links there, and
  Copy link / Share link lives in the entry menu.)
- Star or bookmark on an entry: a hand-placed mark meaning "this one,"
  filterable later alongside tags.
- A microphone-device picker in the recorder, for browsers that guess
  wrong about which input is a microphone.

## Future directions, deliberately parked

- The markdown mirror: one file per entry, frontmatter and all, into a
  private vault, making Obsidian a reading room over the archive.
  Parked 2026-08-28; capture, enrichment, and deploy come first. The
  design keeps its seat in CONTEXT.md and ADR 0001 for when it's
  called.
