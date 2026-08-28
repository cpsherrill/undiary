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

    # Derived from audio when it contains speech; recomputable.
    transcript = models.TextField(blank=True, default="")

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
