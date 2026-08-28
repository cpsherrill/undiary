from django.contrib import admin

from .models import Enrichment, Entry, EntryTag, Tag


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


@admin.register(Enrichment)
class EnrichmentAdmin(admin.ModelAdmin):
    list_display = ("entry", "version", "model", "created_at")
    readonly_fields = ("entry", "version", "model", "payload", "created_at")
