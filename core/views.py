import datetime

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone


@login_required
def index(request):
    if request.method == "POST":
        text = (request.POST.get("text") or "").strip()
        if text:
            tz = (request.POST.get("tz") or "UTC")[:64]
            log_date = _parse_date(request.POST.get("log_date")) or timezone.localdate()
            request.user.entries.create(
                raw=text,
                body=text,
                spoken_at=timezone.now(),
                tz=tz,
                log_date=log_date,
            )
        return redirect("index")

    entries = request.user.entries.all()[:50]
    return render(request, "index.html", {"entries": entries})


def _parse_date(value):
    try:
        return datetime.date.fromisoformat(value or "")
    except ValueError:
        return None
