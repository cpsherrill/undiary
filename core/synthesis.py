"""The list-keeper: the corpus-level synthesis sweep of docs/todos.md.
Reads new entries plus the current todo list and proposes new todos,
color attachments, and completions. Proposals only; verdicts belong
to the user, and dismissals are fed back so nothing returns from the
dead.
"""

import json
import logging

import anthropic
from django.conf import settings
from django.db import transaction
from django.db.models import Count
from pydantic import BaseModel

from .models import Entry, SynthesisRun, Tag, Todo, TodoEntry, TodoItem

logger = logging.getLogger(__name__)

MAX_ITEMS = 8
MAX_SEEDS = 6


class NewTodo(BaseModel):
    title: str
    summary: str
    horizon: str
    topic: str = ""
    seed_entry_ids: list[int]
    items: list[str] = []


class AttachColor(BaseModel):
    todo_id: int
    entry_id: int


class Complete(BaseModel):
    todo_id: int
    entry_id: int
    excerpt: str = ""


class SynthesisResult(BaseModel):
    new_todos: list[NewTodo]
    color: list[AttachColor]
    completions: list[Complete]


SYSTEM = """You are the list-keeper for Undiary, a personal diary. You
receive the user's current todos, the titles of dismissed todos, and
new diary entries. You propose, conservatively; the user decides.

- new_todos: only when entries clearly express an intention, task, or
  follow-up worth tracking. Title short and imperative. Summary one or
  two sentences grounded in the entries. horizon is now, soon, or
  someday by urgency. topic gathers: choose the most unifying slug
  from topic_slugs that genuinely covers the todo, or empty; narrow
  descriptors belong on entries as tags, never as topics.
  seed_entry_ids only from the provided entries. items only when the
  entries themselves enumerate concrete steps.
- color: when a new entry adds real detail to an existing todo.
- completions: only when an entry plainly reports the thing done;
  quote the reporting phrase in excerpt.
- Never propose anything resembling a dismissed title. One todo per
  underlying intention; do not shred one intention into many. When
  nothing qualifies, return empty lists."""


def run_synthesis(user, everything=False):
    """One synthesis pass. Returns the SynthesisRun, or None when
    there is nothing new to read."""
    # The cursor is global entry pk, which is correct while the
    # allowlist has one name on it; a second real user would want a
    # per-user cursor.
    last = SynthesisRun.objects.first()
    through = 0 if everything else (last.through_entry_id if last else 0)

    entries = list(
        user.entries.filter(pk__gt=through)
        .exclude(body="")
        .order_by("pk")
        .prefetch_related("entry_tags__tag")
    )
    if not entries:
        return None

    todos = list(
        user.todos.filter(status__in=[Todo.PROPOSED, Todo.OPEN]).select_related("topic")
    )
    dismissed = list(
        user.todos.filter(status=Todo.DISMISSED).values_list("title", flat=True)
    )
    slugs = _topic_vocabulary(user)

    result = _call_model(entries, todos, dismissed, slugs)
    return _apply(user, result, entries)


def _topic_vocabulary(user):
    """Topics gather, so the vocabulary is small on purpose: every
    watched tag, plus free tags that actually recur."""
    watched = list(
        user.tags.filter(kind=Tag.WATCHED, active=True).values_list("slug", flat=True)
    )
    frequent = list(
        user.tags.filter(kind=Tag.FREE)
        .annotate(uses=Count("entry_tags"))
        .filter(uses__gte=3)
        .order_by("-uses")
        .values_list("slug", flat=True)[:15]
    )
    vocabulary = []
    for slug in watched + frequent:
        if slug not in vocabulary:
            vocabulary.append(slug)
    return vocabulary


def _call_model(entries, todos, dismissed, slugs):
    client = anthropic.Anthropic()
    payload = {
        "tag_slugs": slugs,
        "dismissed_titles": dismissed,
        "current_todos": [
            {
                "id": t.pk,
                "title": t.title,
                "summary": t.summary[:300],
                "status": t.status,
                "horizon": t.horizon,
                "topic": t.topic.slug if t.topic else "",
            }
            for t in todos
        ],
        "new_entries": [
            {
                "id": e.pk,
                "log_date": str(e.log_date),
                "tags": [te.tag.slug for te in e.entry_tags.all()],
                "text": e.body[:900],
            }
            for e in entries
        ],
    }
    # Sonnet thinks adaptively by default and thinking spends from the
    # same budget; a small cap truncates the JSON mid-string.
    response = client.messages.parse(
        model=settings.SYNTHESIS_MODEL,
        max_tokens=16000,
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(payload)}],
        output_format=SynthesisResult,
    )
    return response.parsed_output


@transaction.atomic
def _apply(user, result, entries):
    last = SynthesisRun.objects.first()
    entry_ids = {e.pk for e in entries}
    todo_ids = set(
        user.todos.filter(status__in=[Todo.PROPOSED, Todo.OPEN]).values_list(
            "pk", flat=True
        )
    )

    for proposal in result.new_todos:
        seeds = [i for i in proposal.seed_entry_ids if i in entry_ids][:MAX_SEEDS]
        if not seeds:
            continue
        horizon = proposal.horizon if proposal.horizon in dict(Todo.HORIZONS) else Todo.SOON
        topic = Tag.objects.filter(user=user, slug=proposal.topic).first()
        todo = Todo.objects.create(
            user=user,
            title=proposal.title[:120],
            summary=proposal.summary,
            horizon=horizon,
            topic=topic,
        )
        for entry_id in seeds:
            TodoEntry.objects.create(
                todo=todo, entry_id=entry_id, role=TodoEntry.SEED
            )
        for position, text in enumerate(proposal.items[:MAX_ITEMS]):
            TodoItem.objects.create(todo=todo, text=text[:200], position=position)

    for attach in result.color:
        if attach.todo_id in todo_ids and attach.entry_id in entry_ids:
            TodoEntry.objects.get_or_create(
                todo_id=attach.todo_id,
                entry_id=attach.entry_id,
                role=TodoEntry.COLOR,
            )

    for completion in result.completions:
        if completion.todo_id in todo_ids and completion.entry_id in entry_ids:
            TodoEntry.objects.get_or_create(
                todo_id=completion.todo_id,
                entry_id=completion.entry_id,
                role=TodoEntry.COMPLETION,
            )

    return SynthesisRun.objects.create(
        version=(last.version + 1) if last else 1,
        model=settings.SYNTHESIS_MODEL,
        through_entry_id=max(entry_ids),
        payload=result.model_dump(),
    )


# ---- Re-topic: reassign gathering topics to existing todos ------------


class TopicFix(BaseModel):
    todo_id: int
    topic: str = ""


class RetopicResult(BaseModel):
    fixes: list[TopicFix]


RETOPIC_SYSTEM = """You assign gathering topics to todos. For each
todo, choose the single most unifying slug from topic_slugs that
genuinely covers it, or empty when none does. Topics exist so related
todos group together; never pick a narrow descriptor when a broader
provided slug fits. Return a fix for every todo."""


def retopic(user):
    """One derived pass reassigning topics from the current
    vocabulary. Verdicts are untouched; only the topic column moves."""
    vocabulary = _topic_vocabulary(user)
    todos = list(user.todos.exclude(status=Todo.DISMISSED).select_related("topic"))
    if not todos:
        return None

    result = _call_retopic(vocabulary, todos)

    with transaction.atomic():
        by_id = {t.pk: t for t in todos}
        for fix in result.fixes:
            todo = by_id.get(fix.todo_id)
            if todo is None:
                continue
            tag = (
                Tag.objects.filter(user=user, slug=fix.topic).first()
                if fix.topic
                else None
            )
            todo.topic = tag
            todo.save(update_fields=["topic"])
        last = SynthesisRun.objects.first()
        SynthesisRun.objects.create(
            version=(last.version + 1) if last else 1,
            model=settings.SYNTHESIS_MODEL,
            through_entry_id=last.through_entry_id if last else 0,
            payload={"retopic": result.model_dump()},
        )
    return result


def _call_retopic(vocabulary, todos):
    client = anthropic.Anthropic()
    payload = {
        "topic_slugs": vocabulary,
        "todos": [
            {
                "id": t.pk,
                "title": t.title,
                "summary": t.summary[:200],
                "current_topic": t.topic.slug if t.topic else "",
            }
            for t in todos
        ],
    }
    response = client.messages.parse(
        model=settings.SYNTHESIS_MODEL,
        max_tokens=16000,
        system=RETOPIC_SYSTEM,
        messages=[{"role": "user", "content": json.dumps(payload)}],
        output_format=RetopicResult,
    )
    return response.parsed_output
