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
- Service-worker background sync for the outbox, so a queued entry
  can flush even before the app is reopened. (The PWA itself shipped
  2026-08-28 in two halves: install-grade manifest, icons, worker,
  and offline page; then the offline capture queue in IndexedDB with
  in-order flush on reconnect. The captain does not check for
  signal.)
- Permalinks for individual entries, so one note can be pointed at.
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
