from django.contrib import admin

from .models import Entry


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
