from django.core.management.base import BaseCommand

from core.models import Entry
from core.transcription import transcribe_entry


class Command(BaseCommand):
    help = (
        "Transcribe audio entries with no attempt recorded yet. "
        "--all re-transcribes every audio entry (better model, better ears)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", dest="everything")

    def handle(self, *args, **options):
        entries = Entry.objects.exclude(audio_key="")
        if not options["everything"]:
            entries = entries.filter(transcribed_at__isnull=True)

        done = silent = failed = 0
        for entry in entries.iterator():
            try:
                transcribe_entry(entry)
                if entry.transcript:
                    done += 1
                else:
                    silent += 1
            except Exception as exc:
                failed += 1
                self.stderr.write(f"entry {entry.pk}: {exc}")

        self.stdout.write(
            f"transcribed {done}, no speech {silent}, failed {failed}"
        )
