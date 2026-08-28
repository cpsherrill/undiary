# ADR 0004: three-layer tagging

Date: 2026-08-28. Status: accepted.

## Context

One tag list cannot serve three needs: standing personal interests
("always flag project ideas"), per-entry description, and discovery of
themes nobody thought to ask for. A universal taxonomy serves nobody in
particular.

## Decision

Three layers, all per-user.

1. **Watched tags**: slug plus natural-language definition, answered
   yes or no by every enrichment pass, with an excerpt stored on a hit.
   Adding one triggers retroactive re-enrichment of the corpus.
2. **Free tags**: open-vocabulary proposals from the model, per entry.
3. **Emergent themes**: an occasional corpus-wide pass proposes
   promotions into watched tags.

The merge rule from CONTEXT.md governs all three: re-runs replace
model-sourced tags and never touch user-sourced ones.

## Consequences

The first watched tag is `project_idea`. The tags table carries kind,
definition, and active; entry_tags carries source and confidence.
Retroactivity is the point: a watched tag added today reaches the whole
history for about a dime.
