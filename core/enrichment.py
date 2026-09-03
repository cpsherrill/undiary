"""The filing clerk: one Haiku pass per entry, structured output in,
tags and metadata out. Derived, versioned, re-runnable; never
load-bearing for capture.
"""

import json
import logging
import re

import anthropic
from django.conf import settings
from django.db import transaction
from pydantic import BaseModel

from .models import Enrichment, Entry, EntryTag, Tag

logger = logging.getLogger(__name__)

MAX_FREE_TAGS = 8


class WatchedVerdict(BaseModel):
    slug: str
    hit: bool
    excerpt: str = ""


class EnrichmentResult(BaseModel):
    watched: list[WatchedVerdict]
    tags: list[str]
    people: list[str]
    places: list[str]
    projects: list[str]
    summary: str
    mood: str = ""


SYSTEM = """You are the filing clerk for Undiary, a personal diary. You
receive one entry and return structured metadata about it. Rules:

- tags: 3 to 8 free tags, lowercase_with_underscores, concrete over
  abstract, drawn from what the entry is actually about.
- watched: the user's standing interests, each with a definition.
  Answer hit=true only when the entry genuinely matches the
  definition; when true, copy the most relevant short phrase from the
  entry into excerpt, verbatim.
- people, places, projects: only names actually present in the entry.
- summary: one plain sentence, at most twenty words.
- mood: one lowercase word, or empty when unclear.
- lexicon, when provided: the author's proper nouns with meanings.
  Use these spellings, and read ambiguous mentions accordingly."""


def slugify_tag(value):
    return re.sub(r"[^a-z0-9_]+", "_", (value or "").lower()).strip("_")[:64]


def enrich_entry(entry, timeout=None):
    """Run one enrichment pass and apply it. Returns the Enrichment,
    or None when the entry has no text to read yet."""
    text = (entry.body or entry.raw or entry.transcript).strip()
    if not text:
        return None

    watched = list(entry.user.tags.filter(kind=Tag.WATCHED, active=True))
    lexicon = [
        {"phrase": term.phrase, "definition": term.definition}
        for term in entry.user.lexicon_terms.exclude(definition="")
    ]
    result = _call_model(
        watched, text, entry.log_date, timeout=timeout, lexicon=lexicon
    )
    return _apply(entry, result, settings.ENRICHMENT_MODEL)


def _call_model(watched, text, log_date, timeout=None, lexicon=None):
    client = anthropic.Anthropic()
    if timeout is not None:
        client = client.with_options(timeout=timeout, max_retries=0)
    watchlist = [
        {"slug": t.slug, "definition": t.definition} for t in watched
    ]
    lexicon_block = (
        f"Lexicon:\n{json.dumps(lexicon)}\n\n" if lexicon else ""
    )
    response = client.messages.parse(
        model=settings.ENRICHMENT_MODEL,
        max_tokens=1024,
        system=SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Watched tags:\n{json.dumps(watchlist)}\n\n"
                    + lexicon_block
                    + f"Entry, dated {log_date}:\n\n{text}"
                ),
            }
        ],
        output_format=EnrichmentResult,
    )
    return response.parsed_output


@transaction.atomic
def _apply(entry, result, model_name):
    last = entry.enrichments.first()
    enrichment = Enrichment.objects.create(
        entry=entry,
        version=(last.version + 1) if last else 1,
        model=model_name,
        payload=result.model_dump(),
    )

    # The merge rule: model rows are replaced wholesale, user rows are
    # never touched.
    entry.entry_tags.filter(source=EntryTag.MODEL).delete()
    kept_tag_ids = set(entry.entry_tags.values_list("tag_id", flat=True))

    watched_by_slug = {v.slug: v for v in result.watched if v.hit}
    free_slugs = [slugify_tag(t) for t in result.tags[:MAX_FREE_TAGS]]

    for slug in watched_by_slug:
        tag = Tag.objects.filter(user=entry.user, slug=slug).first()
        if tag and tag.id not in kept_tag_ids:
            EntryTag.objects.create(entry=entry, tag=tag, source=EntryTag.MODEL)
            kept_tag_ids.add(tag.id)

    for slug in free_slugs:
        if not slug:
            continue
        tag, _ = Tag.objects.get_or_create(
            user=entry.user, slug=slug, defaults={"kind": Tag.FREE}
        )
        if tag.id not in kept_tag_ids:
            EntryTag.objects.create(entry=entry, tag=tag, source=EntryTag.MODEL)
            kept_tag_ids.add(tag.id)

    return enrichment


def enrich_quietly(entry, timeout=15.0):
    """Best-effort inline pass after a save; failures wait for the
    enrich_pending sweep instead of breaking the request."""
    if settings.PIPELINES_INLINE_DISABLED:
        return
    try:
        enrich_entry(entry, timeout=timeout)
    except Exception:
        logger.exception("inline enrichment failed for entry %s", entry.pk)
