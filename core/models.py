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
