from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.synthesis import run_synthesis


class Command(BaseCommand):
    help = (
        "Run the synthesis sweep: propose todos, color, and completions "
        "from entries newer than the last run. --all rereads everything."
    )

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", dest="everything")

    def handle(self, *args, **options):
        for user in get_user_model().objects.filter(entries__isnull=False).distinct():
            try:
                run = run_synthesis(user, everything=options["everything"])
            except Exception as exc:
                self.stderr.write(f"synthesis for {user.username}: {exc}")
                continue
            if run is None:
                self.stdout.write("nothing new to synthesize")
            else:
                p = run.payload
                self.stdout.write(
                    "synthesis v%s: proposed %d, colored %d, completions %d"
                    % (
                        run.version,
                        len(p.get("new_todos", [])),
                        len(p.get("color", [])),
                        len(p.get("completions", [])),
                    )
                )
