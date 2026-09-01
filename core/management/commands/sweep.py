from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "The backstop, in order: transcribe pending audio, enrich "
        "pending entries, then synthesize todos, so a fresh transcript "
        "is read and weighed the same pass."
    )

    def handle(self, *args, **options):
        call_command("transcribe_pending", stdout=self.stdout, stderr=self.stderr)
        call_command("enrich_pending", stdout=self.stdout, stderr=self.stderr)
        call_command("synthesize", stdout=self.stdout, stderr=self.stderr)
