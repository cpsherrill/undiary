# ADR 0001: Postgres is the system of record

Date: 2026-08-28. Status: accepted.

## Context

The permanent record could live in Postgres, in markdown files in git
(the Obsidian-as-database posture), or in Firestore alongside the rest
of the fleet. The app is mostly a search-and-metadata problem:
full-text search and tag filters now, embeddings later.

## Decision

Postgres, with a one-way markdown mirror into a private vault.

Markdown-as-database fails on the write path: Obsidian Sync has no
server API, git sync from a phone invites conflicts, and search over
files means building an indexer, which is a database with extra steps.
Firestore fails on the read path: no native full-text search, so the
core feature would depend on a third-party index from day one.

Postgres covers all three phases with one technology: tsvector now,
JSONB for enrichment payloads now, pgvector later.

## Consequences

The mirror gives us the plain-text archive and Obsidian's graph for
free, as a derived export, never a write path. The mirror target is
private; this repository is public and never contains entries.
