import datetime
import mimetypes
import uuid

from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from . import enrichment, search, transcription

# MediaRecorder produces webm (Chrome, Firefox) or mp4 (Safari).
AUDIO_EXTENSIONS = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}


@login_required
def index(request):
    if request.method == "POST":
        text = (request.POST.get("text") or "").strip()
        upload = request.FILES.get("audio")
        if text or upload:
            audio_key = _store_audio(upload) if upload else ""
            tz = (request.POST.get("tz") or "UTC")[:64]
            log_date = _parse_date(request.POST.get("log_date")) or timezone.localdate()
            entry = request.user.entries.create(
                raw=text,
                body=text,
                audio_key=audio_key,
                spoken_at=_parse_spoken_at(request.POST.get("spoken_at")),
                tz=tz,
                log_date=log_date,
            )
            if audio_key:
                transcription.transcribe_quietly(entry)
            enrichment.enrich_quietly(entry)
        return redirect("index")

    q = (request.GET.get("q") or "").strip()
    if q:
        entries = search.search_entries(request.user, q).prefetch_related(
            "entry_tags__tag"
        )[:100]
    else:
        entries = request.user.entries.prefetch_related("entry_tags__tag")[:50]
    return render(request, "index.html", {"entries": entries, "q": q})


@login_required
def entry_detail(request, pk):
    entry = get_object_or_404(
        request.user.entries.prefetch_related("entry_tags__tag"), pk=pk
    )
    return render(request, "entry.html", {"entry": entry})


@login_required
def entry_audio(request, pk):
    entry = get_object_or_404(request.user.entries.exclude(audio_key=""), pk=pk)
    content_type = (
        mimetypes.guess_type(entry.audio_key)[0] or "application/octet-stream"
    )
    return FileResponse(
        default_storage.open(entry.audio_key), content_type=content_type
    )


def offline(request):
    return render(request, "offline.html")


def service_worker(request):
    # Served at /sw.js so its scope covers the whole origin.
    from django.contrib.staticfiles import finders

    with open(finders.find("sw.js")) as f:
        source = f.read()
    response = HttpResponse(source, content_type="text/javascript")
    response["Cache-Control"] = "no-cache"
    return response


@login_required
@require_POST
def entry_star(request, pk):
    entry = request.user.entries.filter(pk=pk).first()
    if entry:
        entry.starred = not entry.starred
        entry.save(update_fields=["starred", "edited_at"])
    referer = request.headers.get("Referer", "")
    if referer.startswith(request.build_absolute_uri("/")):
        return redirect(referer)
    return redirect("index")


@login_required
@require_POST
def entry_delete(request, pk):
    # Quietly succeed when the entry is already gone (double-submits,
    # refreshes): the goal state is reached either way. Filtering by
    # owner also means other users' entries are indistinguishable from
    # deleted ones.
    entry = request.user.entries.filter(pk=pk).first()
    if entry:
        audio_key = entry.audio_key
        entry.delete()
        if audio_key:
            try:
                default_storage.delete(audio_key)
            except Exception:
                # The row is gone either way; an orphaned blob is the
                # cheaper failure, so cleanup stays best-effort.
                pass
    return redirect("index")


def _store_audio(upload):
    base_type = (upload.content_type or "").split(";")[0].strip().lower()
    ext = AUDIO_EXTENSIONS.get(base_type, "bin")
    return default_storage.save(f"audio/{uuid.uuid4().hex}.{ext}", upload)


def _parse_date(value):
    try:
        return datetime.date.fromisoformat(value or "")
    except ValueError:
        return None


def _parse_spoken_at(value):
    """An entry synced from the offline outbox carries the instant it
    was actually composed; anything absent, malformed, or naive means
    now."""
    if value:
        parsed = parse_datetime(value)
        if parsed and timezone.is_aware(parsed):
            return parsed
    return timezone.now()
