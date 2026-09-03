from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import models
from django.utils import timezone


class Entry(models.Model):
    """One moment's note. Text, audio, or both; never neither.

    Capture is immutable: `raw` and `audio_key` are written once.
    `transcript` is derived from audio later and may be recomputed.
    `body` is the editable display copy.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="entries"
    )

    # Capture (immutable once written).
    raw = models.TextField(blank=True, default="")
    audio_key = models.CharField(max_length=1024, blank=True, default="")

    # Derived from audio when it contains speech; recomputable. The
    # timestamp records that an attempt finished, even a silent one,
    # so "no speech" is a state and not a retry loop.
    transcript = models.TextField(blank=True, default="")
    transcribed_at = models.DateTimeField(null=True, blank=True)

    # Editable display copy, initialized from raw or transcript.
    body = models.TextField(blank=True, default="")

    # The instant, the place's clock, and the diary day it belongs to.
    spoken_at = models.DateTimeField(default=timezone.now)
    tz = models.CharField(max_length=64, default="UTC")
    log_date = models.DateField()

    # A hand-placed mark meaning "this one." User judgment is capture.
    starred = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-spoken_at"]
        verbose_name_plural = "entries"
        constraints = [
            models.CheckConstraint(
                condition=~(models.Q(raw="") & models.Q(audio_key="")),
                name="entry_has_text_or_audio",
            ),
        ]

    def __str__(self):
        text = self.body or self.raw or "(audio)"
        return f"{self.log_date}: {text[:60]}"

    @property
    def local_spoken_at(self):
        # Naive on purpose: Django templates re-convert aware datetimes
        # to the active timezone, which would undo this conversion.
        try:
            local = self.spoken_at.astimezone(ZoneInfo(self.tz))
        except (KeyError, ValueError):
            local = self.spoken_at
        return local.replace(tzinfo=None)


# Words the transcriber should know how to spell. Definitions are for
# the reading models, not the ear.
DEFAULT_LEXICON = [
    "Undiary",
    "Crowable",
    "FOSAIC",
    "Wispr Flow",
    "Pindifferent",
    "Tinderbox",
    "Alder Box",
    "FishMash",
    "JokeJudge",
]


class LexiconTerm(models.Model):
    """A spelling the transcriber is biased toward, with an optional
    definition for the text models. Distinct from tags: lexicon terms
    are cased proper nouns for the ear; tags are slugs for the filing."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="lexicon_terms",
    )
    phrase = models.CharField(max_length=100)
    definition = models.TextField(blank=True, default="")
    boost = models.FloatField(default=10.0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["phrase"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "phrase"], name="one_phrase_per_user"
            ),
        ]

    def __str__(self):
        return self.phrase

    @classmethod
    def ensure_defaults(cls, user):
        for phrase in DEFAULT_LEXICON:
            cls.objects.get_or_create(user=user, phrase=phrase)


# The first watched tag every user starts with; more arrive by hand.
DEFAULT_WATCHED_TAGS = {
    "project_idea": (
        "An idea for something the author might build, make, or start, "
        "however offhand or unlikely."
    ),
}


class Tag(models.Model):
    """A label scoped to one user. Watched tags carry a definition and
    are answered yes-or-no by every enrichment pass; free tags are the
    model's open vocabulary."""

    WATCHED = "watched"
    FREE = "free"
    KINDS = [(WATCHED, "watched"), (FREE, "free")]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tags"
    )
    slug = models.SlugField(max_length=64, allow_unicode=False)
    name = models.CharField(max_length=80, blank=True, default="")
    kind = models.CharField(max_length=8, choices=KINDS, default=FREE)
    definition = models.TextField(blank=True, default="")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["slug"]
        constraints = [
            models.UniqueConstraint(fields=["user", "slug"], name="tag_slug_per_user"),
        ]

    def __str__(self):
        return f"{self.slug} ({self.kind})"

    @classmethod
    def ensure_defaults(cls, user):
        for slug, definition in DEFAULT_WATCHED_TAGS.items():
            cls.objects.get_or_create(
                user=user,
                slug=slug,
                defaults={"kind": cls.WATCHED, "definition": definition},
            )


class EntryTag(models.Model):
    """A tag on an entry. The merge rule lives on `source`: re-enrichment
    replaces model rows and never touches user rows."""

    MODEL = "model"
    USER = "user"
    SOURCES = [(MODEL, "model"), (USER, "user")]

    entry = models.ForeignKey(
        Entry, on_delete=models.CASCADE, related_name="entry_tags"
    )
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="entry_tags")
    source = models.CharField(max_length=8, choices=SOURCES, default=MODEL)
    confidence = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["tag__slug"]
        constraints = [
            models.UniqueConstraint(fields=["entry", "tag"], name="one_tag_per_entry"),
        ]

    def __str__(self):
        return f"{self.entry_id}: {self.tag}"


class Todo(models.Model):
    """A derived object synthesized across entries. Existence, summary,
    and links are derived; the user's verdicts (status, horizon,
    checked items, edits) are capture. See docs/todos.md."""

    PROPOSED = "proposed"
    OPEN = "open"
    DONE = "done"
    DISMISSED = "dismissed"
    STATUSES = [(s, s) for s in (PROPOSED, OPEN, DONE, DISMISSED)]

    NOW = "now"
    SOON = "soon"
    SOMEDAY = "someday"
    HORIZONS = [(h, h) for h in (NOW, SOON, SOMEDAY)]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="todos"
    )
    title = models.CharField(max_length=120)
    summary = models.TextField(blank=True, default="")
    status = models.CharField(max_length=9, choices=STATUSES, default=PROPOSED)
    horizon = models.CharField(max_length=8, choices=HORIZONS, default=SOON)
    topic = models.ForeignKey(
        Tag, null=True, blank=True, on_delete=models.SET_NULL, related_name="todos"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.status})"

    @property
    def completion_links(self):
        return [te for te in self.todo_entries.all() if te.role == TodoEntry.COMPLETION]


class TodoItem(models.Model):
    todo = models.ForeignKey(Todo, on_delete=models.CASCADE, related_name="items")
    text = models.CharField(max_length=200)
    done = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.text


class TodoEntry(models.Model):
    """The provenance link. An entry seeds a todo, colors it, or
    reports it complete. Entry deletion removes the link, never the
    todo (FR10)."""

    SEED = "seed"
    COLOR = "color"
    COMPLETION = "completion"
    ROLES = [(r, r) for r in (SEED, COLOR, COMPLETION)]

    MODEL = "model"
    USER = "user"
    SOURCES = [(s, s) for s in (MODEL, USER)]

    todo = models.ForeignKey(Todo, on_delete=models.CASCADE, related_name="todo_entries")
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="todo_entries")
    role = models.CharField(max_length=10, choices=ROLES)
    source = models.CharField(max_length=8, choices=SOURCES, default=MODEL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["todo", "entry", "role"], name="one_role_per_todo_entry"
            ),
        ]

    def __str__(self):
        return f"{self.todo_id} <- {self.entry_id} ({self.role})"


class SynthesisRun(models.Model):
    """Audit trail of the corpus-level sweep: what ran, over what, and
    what it proposed, so re-runs and debugging stay boring."""

    version = models.PositiveIntegerField(unique=True)
    model = models.CharField(max_length=100)
    through_entry_id = models.PositiveIntegerField(default=0)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]

    def __str__(self):
        return f"synthesis v{self.version} ({self.model})"


class Enrichment(models.Model):
    """One model pass over one entry, stored whole. Versions append;
    the latest wins for display; nothing here is load-bearing for
    capture."""

    entry = models.ForeignKey(
        Entry, on_delete=models.CASCADE, related_name="enrichments"
    )
    version = models.PositiveIntegerField()
    model = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["entry", "version"], name="one_version_per_entry"
            ),
        ]

    def __str__(self):
        return f"{self.entry_id} v{self.version} ({self.model})"
