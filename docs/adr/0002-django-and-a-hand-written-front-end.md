# ADR 0002: Django, Postgres, and a hand-written front end

Date: 2026-08-28. Status: accepted.

## Context

Candidates: Django with server-rendered pages, TypeScript on Supabase,
or Firebase functions like the rest of the fleet. One user, low
traffic, and a pipeline with ambitions.

## Decision

Django and Postgres on Cloud Run, GCS for audio, hand-written HTML,
CSS, and vanilla JavaScript in front. No build step.

Three reasons. Django admin is a free management UI over entries, tags,
and enrichments, which for a personal data tool is half the product.
The enrichment pipeline is Python's home turf, and that is where the
ambitions live. And django-allauth does Google sign-in with an
allowlist as configuration, not code.

Supabase is a fine stack but a new platform, with the pipeline squeezed
into edge functions. Firestore lost in ADR 0001.

## Consequences

The one real cost line is managed Postgres (Cloud SQL at roughly ten
dollars a month, or Neon's free tier; undecided, see DEPLOY.md).
Everything else rounds to zero at one user. The front end stays in the
house style: no framework, no build.
