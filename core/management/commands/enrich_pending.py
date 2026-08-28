from django.core.management.base import BaseCommand

from core.enrichment import enrich_entry
from core.models import Entry


class Command(BaseCommand):
    help = (
        "Enrich entries that have text but no enrichment yet. "
        "--all re-enriches everything (after watchlist changes)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", dest="everything")

    def handle(self, *args, **options):
        entries = Entry.objects.all()
        if not options["everything"]:
            entries = entries.filter(enrichments__isnull=True)

        done = skipped = failed = 0
        for entry in entries.iterator():
            try:
                if enrich_entry(entry) is None:
                    skipped += 1
                else:
                    done += 1
            except Exception as exc:
                failed += 1
                self.stderr.write(f"entry {entry.pk}: {exc}")

        self.stdout.write(
            f"enriched {done}, skipped {skipped} (no text), failed {failed}"
        )
