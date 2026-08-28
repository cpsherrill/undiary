import datetime
import mimetypes
import uuid

from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
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
                spoken_at=timezone.now(),
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
def entry_audio(request, pk):
    entry = get_object_or_404(request.user.entries.exclude(audio_key=""), pk=pk)
    content_type = (
        mimetypes.guess_type(entry.audio_key)[0] or "application/octet-stream"
    )
    return FileResponse(
        default_storage.open(entry.audio_key), content_type=content_type
    )


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
