import datetime
import hashlib
import mimetypes
import re
import uuid
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
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
            return redirect(f"{reverse('index')}?new={entry.pk}")
        return redirect("index")

    q = (request.GET.get("q") or "").strip()
    notes = _notes_context(request.user, q)
    if _wants_pane(request):
        return _pane_response(request, "_notes_body.html", notes)
    return _render_app(
        request,
        "notes",
        notes,
        _todos_context(request.user, "", ""),
        notes_url=_notes_url(q),
        todos_url=_todos_url("", ""),
    )


@login_required
def todos(request):
    topic = (request.GET.get("topic") or "").strip()
    q = (request.GET.get("q") or "").strip()
    todos_ctx = _todos_context(request.user, q, topic)
    if _wants_pane(request):
        return _pane_response(request, "_todos_body.html", todos_ctx)
    return _render_app(
        request,
        "todos",
        _notes_context(request.user, ""),
        todos_ctx,
        notes_url=_notes_url(""),
        todos_url=_todos_url(q, topic),
    )


# ---- One page, two panes ----------------------------------------------
# Both tabs render into every page so the client can slide between
# them without a load. The pathname says which pane is showing and
# which pane a search applies to; the other pane arrives unfiltered.


def _notes_context(user, q):
    if q:
        entries = search.search_entries(user, q).prefetch_related(
            "entry_tags__tag", "todo_entries__todo"
        )[:100]
    else:
        entries = user.entries.prefetch_related(
            "entry_tags__tag", "todo_entries__todo"
        )[:50]
    return {"entries": _with_todo_refs(entries), "q": q}


def _with_todo_refs(entries):
    """Attach each entry's linked todos, deduped across roles. A
    read-time courtesy chip; the data still flows one way."""
    entries = list(entries)
    for entry in entries:
        entry.todo_refs = list(
            {te.todo.pk: te.todo for te in entry.todo_entries.all()}.values()
        )
    return entries


def _todos_context(user, q, topic):
    from django.db.models import Q

    from .models import Todo

    qs = user.todos.select_related("topic").prefetch_related(
        "items", "todo_entries__entry"
    )
    if topic:
        qs = qs.filter(topic__slug=topic)
    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(summary__icontains=q)
            | Q(items__text__icontains=q)
        ).distinct()
    outstanding = user.todos.filter(status__in=[Todo.PROPOSED, Todo.OPEN]).count()
    todos_all = list(qs)
    proposed = [t for t in todos_all if t.status == Todo.PROPOSED]
    open_todos = [t for t in todos_all if t.status == Todo.OPEN]
    horizons = [
        (h, [t for t in open_todos if t.horizon == h])
        for h in (Todo.NOW, Todo.SOON, Todo.SOMEDAY)
    ]
    done = [t for t in todos_all if t.status == Todo.DONE][:20]
    dismissed = [t for t in todos_all if t.status == Todo.DISMISSED][:20]
    return {
        "proposed": proposed,
        "horizons": horizons,
        "done": done,
        "dismissed": dismissed,
        "topic": topic,
        "todo_q": q,
        "outstanding": outstanding,
    }


def _notes_url(q):
    return reverse("index") + (f"?{urlencode({'q': q})}" if q else "")


def _todos_url(q, topic):
    params = {key: value for key, value in (("q", q), ("topic", topic)) if value}
    return reverse("todos") + (f"?{urlencode(params)}" if params else "")


def _wants_pane(request):
    """app.js asks for a pane body alone when refreshing one in place."""
    return request.headers.get("X-Pane") == "1"


_CSRF_VALUE = re.compile(r'name="csrfmiddlewaretoken" value="[^"]*"')


def _render_body(request, template, context):
    """A pane body and its fingerprint, so the client can tell a changed
    pane from a merely re-rendered one. The CSRF token is masked afresh
    on every render and stays out of the hash."""
    html = render_to_string(template, context, request=request)
    digest = hashlib.sha256(_CSRF_VALUE.sub("", html).encode()).hexdigest()[:16]
    return html, digest


def _pane_response(request, template, context):
    html, digest = _render_body(request, template, context)
    response = HttpResponse(html)
    response["X-Pane-Hash"] = digest
    response["Cache-Control"] = "no-store"
    return response


def _render_app(request, active, notes, todos, notes_url, todos_url):
    notes_html, notes_hash = _render_body(request, "_notes_body.html", notes)
    todos_html, todos_hash = _render_body(request, "_todos_body.html", todos)
    return render(
        request,
        "app.html",
        {
            "active_tab": active,
            "notes_body": notes_html,
            "notes_hash": notes_hash,
            "notes_url": notes_url,
            "todos_body": todos_html,
            "todos_hash": todos_hash,
            "todos_url": todos_url,
        },
    )


@login_required
def entry_detail(request, pk):
    entry = get_object_or_404(
        request.user.entries.prefetch_related(
            "entry_tags__tag", "todo_entries__todo"
        ),
        pk=pk,
    )
    entry = _with_todo_refs([entry])[0]
    return render(request, "entry.html", {"entry": entry, "active_tab": "notes"})


@login_required
@require_POST
def todo_create(request):
    from .models import Todo

    title = (request.POST.get("title") or "").strip()[:120]
    horizon = request.POST.get("horizon", Todo.SOON)
    if title:
        request.user.todos.create(
            title=title,
            status=Todo.OPEN,
            horizon=horizon if horizon in dict(Todo.HORIZONS) else Todo.SOON,
            decided_at=timezone.now(),
        )
    return redirect("todos")


@login_required
@require_POST
def todo_note(request, pk):
    """A thought added to a todo is a diary entry that flows forward:
    it lands in the log, gets enriched like any note, and links to the
    todo as user-sourced color. The tab law holds."""
    from .models import TodoEntry

    todo = request.user.todos.filter(pk=pk).first()
    text = (request.POST.get("text") or "").strip()
    if todo and text:
        entry = request.user.entries.create(
            raw=text,
            body=text,
            spoken_at=timezone.now(),
            tz=(request.POST.get("tz") or "UTC")[:64],
            log_date=_parse_date(request.POST.get("log_date")) or timezone.localdate(),
        )
        TodoEntry.objects.get_or_create(
            todo=todo, entry=entry, role=TodoEntry.COLOR,
            defaults={"source": TodoEntry.USER},
        )
        enrichment.enrich_quietly(entry)
    return redirect("todos")


@login_required
@require_POST
def todo_verdict(request, pk, action):
    from .models import Todo

    transitions = {
        "accept": ([Todo.PROPOSED], Todo.OPEN, "decided_at"),
        "dismiss": ([Todo.PROPOSED, Todo.OPEN], Todo.DISMISSED, "decided_at"),
        "done": ([Todo.OPEN], Todo.DONE, "done_at"),
        "reopen": ([Todo.DONE], Todo.OPEN, None),
        "restore": ([Todo.DISMISSED], Todo.PROPOSED, None),
    }
    if action not in transitions:
        return redirect("todos")
    allowed_from, target, stamp = transitions[action]
    todo = request.user.todos.filter(pk=pk, status__in=allowed_from).first()
    if todo:
        todo.status = target
        if stamp:
            setattr(todo, stamp, timezone.now())
        if action == "reopen":
            todo.done_at = None
        if action == "restore":
            todo.decided_at = None
        todo.save()
    return redirect("todos")


@login_required
@require_POST
def todo_item_add(request, pk):
    from django.db.models import Max

    from .models import TodoItem

    todo = request.user.todos.filter(pk=pk).first()
    text = (request.POST.get("text") or "").strip()[:200]
    if todo and text:
        last = todo.items.aggregate(Max("position"))["position__max"]
        TodoItem.objects.create(
            todo=todo, text=text, position=(last + 1) if last is not None else 0
        )
    return redirect("todos")


@login_required
@require_POST
def todo_item_toggle(request, pk):
    from .models import TodoItem

    item = TodoItem.objects.filter(pk=pk, todo__user=request.user).first()
    if item:
        item.done = not item.done
        item.save(update_fields=["done"])
    return redirect("todos")


@login_required
@require_POST
def todo_horizon(request, pk):
    from .models import Todo

    horizon = request.POST.get("horizon", "")
    todo = request.user.todos.filter(pk=pk).first()
    if todo and horizon in dict(Todo.HORIZONS):
        todo.horizon = horizon
        todo.save(update_fields=["horizon"])
    return redirect("todos")


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


def loading(request):
    return render(request, "loading.html")


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
