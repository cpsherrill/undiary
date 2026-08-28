"""One search box, two languages: plain words run full-text search,
#tag tokens filter by tag, and the two compose. Postgres does the
ranking in production; dev SQLite falls back to substring matching.

Query-time tsvectors are plenty at one user's volume; a generated
column with a GIN index is the upgrade path when that stops being
true.
"""

import re

from django.db import connection
from django.db.models import Q

TAG_TOKEN = re.compile(r"#([A-Za-z0-9_]+)")


def parse_query(q):
    q = (q or "").strip()
    tags = [t.lower() for t in TAG_TOKEN.findall(q)]
    text = TAG_TOKEN.sub(" ", q)
    text = re.sub(r"\s+", " ", text).strip()
    return text, tags


def search_entries(user, q):
    text, tags = parse_query(q)
    entries = user.entries.all()

    # Each chained filter is its own join, so several tags mean AND.
    for slug in tags:
        entries = entries.filter(entry_tags__tag__slug=slug)

    if text:
        if connection.vendor == "postgresql":
            from django.contrib.postgres.search import (
                SearchQuery,
                SearchRank,
                SearchVector,
            )

            vector = SearchVector("body", weight="A") + SearchVector(
                "transcript", weight="B"
            )
            query = SearchQuery(text, search_type="websearch")
            entries = (
                entries.annotate(search=vector, rank=SearchRank(vector, query))
                .filter(search=query)
                .order_by("-rank", "-spoken_at")
            )
        else:
            entries = entries.filter(
                Q(body__icontains=text) | Q(transcript__icontains=text)
            )

    return entries.distinct()
