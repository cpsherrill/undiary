from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.synthesis import retopic


class Command(BaseCommand):
    help = "Reassign gathering topics to all non-dismissed todos."

    def handle(self, *args, **options):
        for user in get_user_model().objects.filter(todos__isnull=False).distinct():
            try:
                result = retopic(user)
            except Exception as exc:
                self.stderr.write(f"retopic for {user.username}: {exc}")
                continue
            if result is None:
                self.stdout.write("no todos to retopic")
            else:
                self.stdout.write(f"retopiced {len(result.fixes)} todos")
