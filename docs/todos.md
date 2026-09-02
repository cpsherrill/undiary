# The list: design for Undiary's todo layer

> The captain never files anything, and now the captain never writes
> the list either. You talk; the computer notices what wants doing,
> watches for it getting done, and keeps the receipts.

Status: design settled 2026-08-31 (see
[ADR 0005](adr/0005-todos-are-a-derived-layer.md)); all open
questions answered by Colin the same day. Not built yet.

## Vision

Entries already contain intentions ("follow up on the car sticker"),
elaborations, and reports of completion ("the sticker is on the car"),
with nothing connecting them. The todo layer is the object that
notices: it synthesizes todos out of entries, attaches later entries
as detail, proposes closure when a note reports the deed done, and
keeps every link, so a finished todo reads like a small story told in
your own notes.

## Principles

1. **The law applies.** A todo's existence, summary, and entry links
   are derived and re-runnable. The user's verdicts (status, horizon,
   checked items) are capture; no re-run touches them.
2. **One-way flow (the tab law).** Notes feed todos, never the
   reverse. Verdicts live on todos and do not create entries. The log
   page grows no task chrome, ever; a passive provenance chip linking
   an entry to the todo it fed is display, not flow.
3. **Proposals sit quietly.** The sweep never notifies, badges, or
   nags. Proposals wait in the Todos tab until looked at.
4. **Austerity guardrail.** The todo surface is a grouped list with
   verdicts and links. The day it wants swimlanes is the day it wants
   a GitHub sync instead.
5. **Provenance is the product.** Undiary owns its todos because it
   owns their sources. External trackers and agents get mirrors and
   dispatches later, never custody.

## The two tabs

A small nav under the header: **Notes** and **Todos**. Notes is the
existing page, unchanged. Todos shows:

- **Proposed**: new todos awaiting a verdict, each with its seed
  note(s) quoted small. Accept or dismiss, one tap each.
- **Open**: accepted todos grouped by horizon (now, soon, someday) and
  filterable by topic. Each shows title, summary, line items with
  checkboxes, linked notes by role, and a done button.
- **Done**: the archive, each closed todo showing its completion
  note(s) alongside its seeds.

## Data model

- `todos`: user, title, summary (derived text, user-editable), status
  (proposed, open, done, dismissed), horizon (now, soon, someday),
  topic tag (nullable FK to tags), created_at, decided_at, done_at.
  No due dates in v1; horizons carry the urgency until they cannot.
- `todo_items`: todo FK, text, done (bool), position.
- `todo_entries`: todo FK, entry FK, role (seed, color, completion),
  source (model, user), created_at. Unique per (todo, entry, role).
- `synthesis_runs`: version, model, entry window covered, payload of
  raw proposals, created_at. The audit trail that makes re-runs and
  debugging boring.

Dismissed todos are remembered and shown to the model so it does not
re-propose them; dismissal is a verdict, not an absence.

## The synthesis sweep

Third phase of `manage.py sweep`, after transcription and enrichment:

1. Input: entries since the last run (body, tags, dates), plus a
   compact summary of every open and proposed todo, plus the dismissed
   list as a do-not-repropose set.
2. One structured-output call to the synthesis model, Sonnet
   (corpus reasoning earns the bigger model; the versioned runs table
   makes changing it boring). Output: proposals of
   exactly three kinds: `new_todo` (title, summary, horizon guess,
   suggested topic, seed entry ids), `attach_color` (todo id, entry
   id), `complete` (todo id, completion entry id, evidence excerpt).
3. Apply: new todos land as `proposed`; color attaches immediately
   (derived, harmless); completions mark the todo `proposed-done`? No:
   completions attach the entry with role `completion` and surface a
   one-tap "mark done" affordance on the open todo. Nothing closes
   without a verdict.
4. `--all` re-synthesizes from the beginning, respecting verdicts as
   always.

## Requirements, v1

- FR1: the sweep proposes new todos with seed links from unprocessed
  entries.
- FR2: the sweep attaches later relevant entries to existing todos as
  color.
- FR3: the sweep detects completion reports and surfaces them on the
  todo; a verdict closes it.
- FR4: verdicts: accept, dismiss, done, reopen; horizon editable;
  title and summary editable (edits stick; re-runs must not clobber,
  same as user tags).
- FR5: line items: model may propose them inside a new todo; the user
  can add, edit, check, and delete them.
- FR6: topics reuse the tags table; grouping and filtering by topic
  and horizon in the Todos tab.
- FR7: every todo renders its linked notes with permalinks, by role.
- FR8: full retroactive synthesis over the existing corpus at launch.
- FR9: proposals are silent; no notification surface of any kind.
- FR10: deleting an entry never deletes a todo; the link row goes, the
  todo stays, honest about a missing source.

## Later, deliberately

- Dispatch: push a todo outward through the extensibility hooks (a
  GitHub issue or project item, an agent handoff for repo-shaped
  work), with status mirrored back by note or by hook.
- `is:todo`-style search integration on the Notes tab.
- Digest views (what closed this month, told via the linked notes).

## Decisions (Colin, 2026-08-31)

- A done verdict writes nothing to the log. The tab law stays pure.
- Now, soon, and someday are the whole of urgency in v1; no due
  dates.
- Topics are reused tags, until they creak.
- The synthesis model is Sonnet; corpus reasoning earns it.
- The 15-minute sweep cadence is enough; no inline synthesis nudge.
