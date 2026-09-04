# ADR 0005: todos are a derived layer, not a second app

Date: 2026-08-31. Status: accepted.

## Context

Notes keep arriving that are todo-shaped: standing intentions, feature
requests, follow-ups. Some later notes report those things done. The
question was whether the todo system is a second app fed by exports, a
service inside Undiary, or a handoff to an external tracker.

## Decision

One app, two surfaces, one-way flow. Todos are a derived layer inside
Undiary: a synthesis sweep reads entries and proposes todos, color,
and completions; the user renders verdicts. The Todos tab is a
separate page over the same database; the log page stays free of task
chrome. In code, todos consume entries and entries never import todos,
so a future extraction line is pre-drawn but uncrossed.

Amended 2026-09-04: both surfaces now render into one page and the
client slides between them, so a tab switch costs no load. That is a
change of display, not of flow. Each pane's body is refreshed from the
server by fingerprint after it comes into view, and every write inside
a pane (a verdict, a new todo, a new entry) answers with that pane's
fresh body, so nothing on the two tabs reloads. The forms above each
body are never replaced, so a draft or a running recording survives
the swap.

A second app would put an API wall through a one-user database and
sever the note-to-todo provenance that is the whole point. An external
tracker as the record would do the same; external systems (GitHub
issues and projects, eventually agents) get mirrors and dispatches,
never custody.

## Consequences

The merge rule extends upward: derived halves of a todo (existence,
summary, links) are re-runnable; verdict halves (status, horizon, due
date, checked line items) are capture and untouchable. The sweep gains
a third phase after transcription and enrichment. The full design
lives in [docs/todos.md](../todos.md).
