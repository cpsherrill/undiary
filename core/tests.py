import datetime
import shutil
import tempfile

from allauth.socialaccount.models import SocialLogin
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .adapters import AllowlistSocialAdapter, promote_if_admin
from .models import Entry

User = get_user_model()


def make_user(email="colin@example.com"):
    return User.objects.create_user(username=email, email=email)


class EntryModelTests(TestCase):
    def test_entry_requires_text_or_audio(self):
        user = make_user()
        with self.assertRaises(IntegrityError):
            Entry.objects.create(user=user, log_date=datetime.date(2026, 8, 28))

    def test_text_only_entry_is_fine(self):
        user = make_user()
        entry = Entry.objects.create(
            user=user, raw="hello", body="hello", log_date=datetime.date(2026, 8, 28)
        )
        self.assertEqual(entry.body, "hello")

    def test_audio_only_entry_is_fine(self):
        user = make_user()
        entry = Entry.objects.create(
            user=user, audio_key="audio/x.webm", log_date=datetime.date(2026, 8, 28)
        )
        self.assertEqual(entry.body, "")

    def test_local_spoken_at_uses_entry_tz(self):
        user = make_user()
        entry = Entry.objects.create(
            user=user,
            raw="x",
            log_date=datetime.date(2026, 8, 28),
            spoken_at=timezone.datetime(
                2026, 8, 28, 12, 0, tzinfo=datetime.timezone.utc
            ),
            tz="America/New_York",
        )
        self.assertEqual(entry.local_spoken_at.hour, 8)

    def test_bad_tz_falls_back_to_utc_instant(self):
        user = make_user()
        entry = Entry.objects.create(
            user=user, raw="x", log_date=datetime.date(2026, 8, 28), tz="Mars/Olympus"
        )
        self.assertEqual(entry.local_spoken_at, entry.spoken_at.replace(tzinfo=None))


class IndexViewTests(TestCase):
    def test_anonymous_is_sent_to_sign_in(self):
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_post_creates_an_entry(self):
        user = make_user()
        self.client.force_login(user)
        response = self.client.post(
            reverse("index"),
            {"text": "First entry.", "tz": "America/New_York", "log_date": "2026-08-27"},
        )
        self.assertRedirects(response, reverse("index"))
        entry = user.entries.get()
        self.assertEqual(entry.raw, "First entry.")
        self.assertEqual(entry.body, "First entry.")
        self.assertEqual(entry.tz, "America/New_York")
        self.assertEqual(entry.log_date, datetime.date(2026, 8, 27))

    def test_blank_post_creates_nothing(self):
        user = make_user()
        self.client.force_login(user)
        self.client.post(reverse("index"), {"text": "   ", "tz": "UTC"})
        self.assertEqual(user.entries.count(), 0)

    def test_bad_date_falls_back_to_today(self):
        user = make_user()
        self.client.force_login(user)
        self.client.post(
            reverse("index"), {"text": "x", "tz": "UTC", "log_date": "not-a-date"}
        )
        self.assertEqual(user.entries.get().log_date, timezone.localdate())

    def test_header_shows_signed_in_identity(self):
        user = make_user()
        self.client.force_login(user)
        response = self.client.get(reverse("index"))
        self.assertContains(response, "colin@example.com")

    def test_header_shows_google_avatar_when_present(self):
        from allauth.socialaccount.models import SocialAccount

        user = make_user()
        SocialAccount.objects.create(
            user=user,
            provider="google",
            uid="123",
            extra_data={"picture": "https://lh3.example.com/photo.jpg"},
        )
        self.client.force_login(user)
        response = self.client.get(reverse("index"))
        self.assertContains(response, "https://lh3.example.com/photo.jpg")

    def test_entries_are_the_users_own(self):
        user = make_user()
        other = make_user("other@example.com")
        Entry.objects.create(user=other, raw="theirs", log_date=datetime.date(2026, 8, 28))
        self.client.force_login(user)
        response = self.client.get(reverse("index"))
        self.assertNotContains(response, "theirs")


@override_settings(UNDIARY_ALLOWED_EMAILS=["colin@example.com"])
class AllowlistTests(TestCase):
    def _sociallogin(self, email):
        return SocialLogin(user=User(username=email, email=email))

    def test_allowlisted_email_may_sign_up(self):
        adapter = AllowlistSocialAdapter()
        self.assertTrue(
            adapter.is_open_for_signup(None, self._sociallogin("colin@example.com"))
        )

    def test_allowlist_is_case_insensitive(self):
        adapter = AllowlistSocialAdapter()
        self.assertTrue(
            adapter.is_open_for_signup(None, self._sociallogin("Colin@Example.com"))
        )

    def test_unknown_email_may_not_sign_up(self):
        adapter = AllowlistSocialAdapter()
        self.assertFalse(
            adapter.is_open_for_signup(None, self._sociallogin("stranger@example.com"))
        )


class AudioTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_root = tempfile.mkdtemp()
        cls.enterClassContext(override_settings(MEDIA_ROOT=cls.media_root))
        cls.addClassCleanup(shutil.rmtree, cls.media_root, ignore_errors=True)

    def _clip(self):
        return SimpleUploadedFile(
            "recording.webm", b"not-really-audio", content_type="audio/webm"
        )

    def test_post_with_text_and_audio_makes_one_entry(self):
        user = make_user()
        self.client.force_login(user)
        self.client.post(
            reverse("index"), {"text": "hummed a tune", "tz": "UTC", "audio": self._clip()}
        )
        entry = user.entries.get()
        self.assertEqual(entry.body, "hummed a tune")
        self.assertTrue(entry.audio_key.startswith("audio/"))
        self.assertTrue(entry.audio_key.endswith(".webm"))

    def test_audio_only_post_makes_an_entry(self):
        user = make_user()
        self.client.force_login(user)
        self.client.post(reverse("index"), {"text": "", "tz": "UTC", "audio": self._clip()})
        entry = user.entries.get()
        self.assertEqual(entry.body, "")
        self.assertTrue(entry.audio_key)

    def test_owner_can_stream_their_audio(self):
        user = make_user()
        self.client.force_login(user)
        self.client.post(reverse("index"), {"tz": "UTC", "audio": self._clip()})
        entry = user.entries.get()
        response = self.client.get(reverse("entry_audio", args=[entry.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"not-really-audio")

    def test_strangers_get_404_for_others_audio(self):
        owner = make_user()
        self.client.force_login(owner)
        self.client.post(reverse("index"), {"tz": "UTC", "audio": self._clip()})
        entry = owner.entries.get()
        self.client.logout()
        stranger = make_user("stranger@example.com")
        self.client.force_login(stranger)
        response = self.client.get(reverse("entry_audio", args=[entry.pk]))
        self.assertEqual(response.status_code, 404)

    def test_text_entry_has_no_audio_endpoint(self):
        user = make_user()
        self.client.force_login(user)
        self.client.post(reverse("index"), {"text": "words only", "tz": "UTC"})
        entry = user.entries.get()
        response = self.client.get(reverse("entry_audio", args=[entry.pk]))
        self.assertEqual(response.status_code, 404)

    def test_delete_removes_entry_and_its_audio_file(self):
        from django.core.files.storage import default_storage

        user = make_user()
        self.client.force_login(user)
        self.client.post(reverse("index"), {"tz": "UTC", "audio": self._clip()})
        entry = user.entries.get()
        self.assertTrue(default_storage.exists(entry.audio_key))
        response = self.client.post(reverse("entry_delete", args=[entry.pk]))
        self.assertRedirects(response, reverse("index"))
        self.assertEqual(user.entries.count(), 0)
        self.assertFalse(default_storage.exists(entry.audio_key))


class EntryDeleteTests(TestCase):
    def _entry(self, user):
        return Entry.objects.create(
            user=user, raw="x", body="x", log_date=datetime.date(2026, 8, 28)
        )

    def test_owner_can_delete(self):
        user = make_user()
        entry = self._entry(user)
        self.client.force_login(user)
        self.client.post(reverse("entry_delete", args=[entry.pk]))
        self.assertEqual(user.entries.count(), 0)

    def test_stranger_cannot_delete(self):
        owner = make_user()
        entry = self._entry(owner)
        stranger = make_user("stranger@example.com")
        self.client.force_login(stranger)
        response = self.client.post(reverse("entry_delete", args=[entry.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(owner.entries.count(), 1)

    def test_get_is_not_allowed(self):
        user = make_user()
        entry = self._entry(user)
        self.client.force_login(user)
        response = self.client.get(reverse("entry_delete", args=[entry.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(user.entries.count(), 1)


@override_settings(UNDIARY_ADMIN_EMAILS=["colin@example.com"])
class AdminPromotionTests(TestCase):
    def test_admin_email_gets_staff_and_superuser(self):
        user = make_user("colin@example.com")
        promote_if_admin(user)
        user.refresh_from_db()
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_other_allowlisted_email_stays_regular(self):
        user = make_user("other@example.com")
        promote_if_admin(user)
        user.refresh_from_db()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
