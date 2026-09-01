from django.contrib import admin

from .models import (
    Enrichment,
    Entry,
    EntryTag,
    SynthesisRun,
    Tag,
    Todo,
    TodoEntry,
    TodoItem,
)


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = ("log_date", "spoken_at", "user", "short_body")
    list_filter = ("log_date",)
    search_fields = ("body", "raw", "transcript")
    date_hierarchy = "log_date"
    readonly_fields = ("raw", "audio_key", "created_at", "edited_at")

    @admin.display(description="body")
    def short_body(self, obj):
        text = obj.body or obj.raw or "(audio)"
        return text[:80]


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("slug", "kind", "active", "user", "definition")
    list_filter = ("kind", "active")
    list_editable = ("active",)
    search_fields = ("slug", "definition")


@admin.register(EntryTag)
class EntryTagAdmin(admin.ModelAdmin):
    list_display = ("entry", "tag", "source", "confidence")
    list_filter = ("source", "tag__kind")


class TodoItemInline(admin.TabularInline):
    model = TodoItem
    extra = 0


class TodoEntryInline(admin.TabularInline):
    model = TodoEntry
    extra = 0
    raw_id_fields = ("entry",)


@admin.register(Todo)
class TodoAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "horizon", "topic", "created_at")
    list_filter = ("status", "horizon")
    search_fields = ("title", "summary")
    inlines = [TodoItemInline, TodoEntryInline]


@admin.register(SynthesisRun)
class SynthesisRunAdmin(admin.ModelAdmin):
    list_display = ("version", "model", "through_entry_id", "created_at")
    readonly_fields = ("version", "model", "through_entry_id", "payload", "created_at")


@admin.register(Enrichment)
class EnrichmentAdmin(admin.ModelAdmin):
    list_display = ("entry", "version", "model", "created_at")
    readonly_fields = ("entry", "version", "model", "payload", "created_at")
