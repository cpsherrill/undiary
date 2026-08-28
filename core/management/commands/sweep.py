from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "The backstop, in order: transcribe pending audio, then enrich "
        "pending entries, so a fresh transcript gets read the same pass."
    )

    def handle(self, *args, **options):
        call_command("transcribe_pending", stdout=self.stdout, stderr=self.stderr)
        call_command("enrich_pending", stdout=self.stdout, stderr=self.stderr)
