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
from .enrichment import EnrichmentResult, WatchedVerdict, _apply, enrich_entry
from .models import Entry, EntryTag, Tag

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


@override_settings(PIPELINES_INLINE_DISABLED=True)
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
        entry = user.entries.get()
        self.assertRedirects(response, f"/?new={entry.pk}")
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

    def test_synced_entry_keeps_its_spoken_instant(self):
        user = make_user()
        self.client.force_login(user)
        self.client.post(
            reverse("index"),
            {"text": "from the outbox", "tz": "UTC", "spoken_at": "2026-08-28T02:03:04Z"},
        )
        entry = user.entries.get()
        self.assertEqual(
            entry.spoken_at,
            timezone.datetime(2026, 8, 28, 2, 3, 4, tzinfo=datetime.timezone.utc),
        )

    def test_bad_spoken_at_means_now(self):
        user = make_user()
        self.client.force_login(user)
        before = timezone.now()
        self.client.post(
            reverse("index"), {"text": "x", "tz": "UTC", "spoken_at": "not-a-time"}
        )
        self.assertGreaterEqual(user.entries.get().spoken_at, before)

    def test_naive_spoken_at_means_now(self):
        user = make_user()
        self.client.force_login(user)
        before = timezone.now()
        self.client.post(
            reverse("index"),
            {"text": "x", "tz": "UTC", "spoken_at": "2026-08-28T02:03:04"},
        )
        self.assertGreaterEqual(user.entries.get().spoken_at, before)

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


@override_settings(PIPELINES_INLINE_DISABLED=True)
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
        self.assertRedirects(response, reverse("index"))
        self.assertEqual(owner.entries.count(), 1)

    def test_double_delete_quietly_succeeds(self):
        user = make_user()
        entry = self._entry(user)
        self.client.force_login(user)
        self.client.post(reverse("entry_delete", args=[entry.pk]))
        response = self.client.post(reverse("entry_delete", args=[entry.pk]))
        self.assertRedirects(response, reverse("index"))
        self.assertEqual(user.entries.count(), 0)

    def test_get_is_not_allowed(self):
        user = make_user()
        entry = self._entry(user)
        self.client.force_login(user)
        response = self.client.get(reverse("entry_delete", args=[entry.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(user.entries.count(), 1)


def result_fixture(**overrides):
    base = dict(
        watched=[WatchedVerdict(slug="project_idea", hit=True, excerpt="build a birdhouse")],
        tags=["woodworking", "birds"],
        people=["Sam"],
        places=[],
        projects=[],
        summary="Considered building a birdhouse with Sam.",
        mood="hopeful",
    )
    base.update(overrides)
    return EnrichmentResult(**base)


class EnrichmentTests(TestCase):
    def setUp(self):
        self.user = make_user()
        Tag.ensure_defaults(self.user)
        self.entry = Entry.objects.create(
            user=self.user,
            raw="Maybe I build a birdhouse with Sam.",
            body="Maybe I build a birdhouse with Sam.",
            log_date=datetime.date(2026, 8, 28),
        )

    def test_apply_creates_versioned_enrichment_and_tags(self):
        enrichment = _apply(self.entry, result_fixture(), "claude-haiku-4-5")
        self.assertEqual(enrichment.version, 1)
        self.assertEqual(enrichment.payload["summary"][:10], "Considered")
        slugs = set(
            self.entry.entry_tags.values_list("tag__slug", flat=True)
        )
        self.assertEqual(slugs, {"project_idea", "woodworking", "birds"})
        watched = self.entry.entry_tags.get(tag__slug="project_idea")
        self.assertEqual(watched.tag.kind, Tag.WATCHED)

    def test_rerun_replaces_model_tags_and_keeps_user_tags(self):
        _apply(self.entry, result_fixture(), "claude-haiku-4-5")
        keeper = Tag.objects.create(user=self.user, slug="keeper", kind=Tag.FREE)
        EntryTag.objects.create(entry=self.entry, tag=keeper, source=EntryTag.USER)

        second = _apply(
            self.entry,
            result_fixture(watched=[], tags=["carpentry"]),
            "claude-haiku-4-5",
        )
        self.assertEqual(second.version, 2)
        slugs = set(self.entry.entry_tags.values_list("tag__slug", flat=True))
        self.assertEqual(slugs, {"carpentry", "keeper"})
        self.assertEqual(
            self.entry.entry_tags.get(tag__slug="keeper").source, EntryTag.USER
        )

    def test_messy_free_tags_are_slugified(self):
        _apply(
            self.entry,
            result_fixture(watched=[], tags=["Wood Working!", "  ", "birds"]),
            "claude-haiku-4-5",
        )
        slugs = set(self.entry.entry_tags.values_list("tag__slug", flat=True))
        self.assertEqual(slugs, {"wood_working", "birds"})

    def test_audio_only_entry_is_skipped(self):
        silent = Entry.objects.create(
            user=self.user, audio_key="audio/x.webm", log_date=datetime.date(2026, 8, 28)
        )
        self.assertIsNone(enrich_entry(silent))
        self.assertEqual(silent.enrichments.count(), 0)

    def test_enrich_entry_calls_model_and_applies(self):
        from unittest.mock import patch

        with patch("core.enrichment._call_model", return_value=result_fixture()) as call:
            enrichment = enrich_entry(self.entry)
        self.assertEqual(enrichment.version, 1)
        watched_arg = call.call_args.args[0]
        self.assertEqual([t.slug for t in watched_arg], ["project_idea"])

    def test_post_survives_enrichment_failure(self):
        from unittest.mock import patch

        self.client.force_login(self.user)
        with patch("core.enrichment._call_model", side_effect=RuntimeError("api down")):
            response = self.client.post(
                reverse("index"), {"text": "still saved", "tz": "UTC"}
            )
        entry = self.user.entries.get(raw="still saved")
        self.assertRedirects(response, f"/?new={entry.pk}")

    def test_enrich_pending_command_processes_unenriched_only(self):
        from io import StringIO
        from unittest.mock import patch

        from django.core.management import call_command

        _apply(self.entry, result_fixture(), "claude-haiku-4-5")
        Entry.objects.create(
            user=self.user, raw="new one", body="new one",
            log_date=datetime.date(2026, 8, 28),
        )
        out = StringIO()
        with patch("core.enrichment._call_model", return_value=result_fixture()) as call:
            call_command("enrich_pending", stdout=out)
        self.assertEqual(call.call_count, 1)
        self.assertIn("enriched 1", out.getvalue())

    def test_ensure_defaults_is_idempotent(self):
        Tag.ensure_defaults(self.user)
        Tag.ensure_defaults(self.user)
        self.assertEqual(self.user.tags.filter(slug="project_idea").count(), 1)

    def test_tags_render_as_chips(self):
        _apply(self.entry, result_fixture(), "claude-haiku-4-5")
        self.client.force_login(self.user)
        response = self.client.get(reverse("index"))
        self.assertContains(response, "tag-watched")
        self.assertContains(response, "project_idea")
        self.assertContains(response, "woodworking")


@override_settings(PIPELINES_INLINE_DISABLED=False)
class TranscriptionTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_root = tempfile.mkdtemp()
        cls.enterClassContext(override_settings(MEDIA_ROOT=cls.media_root))
        cls.addClassCleanup(shutil.rmtree, cls.media_root, ignore_errors=True)

    def setUp(self):
        self.user = make_user()

    def _audio_entry(self, body=""):
        from django.core.files.storage import default_storage

        key = default_storage.save(
            "audio/test.webm", SimpleUploadedFile("t.webm", b"bytes", "audio/webm")
        )
        return Entry.objects.create(
            user=self.user, body=body, raw=body, audio_key=key,
            log_date=datetime.date(2026, 8, 28),
        )

    def test_transcript_fills_empty_body(self):
        from unittest.mock import patch

        from .transcription import transcribe_entry

        entry = self._audio_entry()
        with patch("core.transcription._recognize", return_value="I spoke words."):
            transcribe_entry(entry)
        entry.refresh_from_db()
        self.assertEqual(entry.transcript, "I spoke words.")
        self.assertEqual(entry.body, "I spoke words.")
        self.assertIsNotNone(entry.transcribed_at)

    def test_long_audio_falls_back_to_segmentation(self):
        from unittest.mock import patch

        from google.api_core.exceptions import InvalidArgument

        from .transcription import transcribe_entry

        entry = self._audio_entry()
        with patch(
            "core.transcription._recognize",
            side_effect=InvalidArgument("Audio can be of a maximum of 60 seconds."),
        ), patch(
            "core.transcription._recognize_segmented",
            return_value="a long thought, stitched",
        ) as seg:
            transcribe_entry(entry)
        entry.refresh_from_db()
        self.assertTrue(seg.called)
        self.assertEqual(entry.transcript, "a long thought, stitched")

    def test_segmentation_failure_leaves_entry_pending(self):
        from unittest.mock import patch

        from google.api_core.exceptions import InvalidArgument

        from .transcription import transcribe_entry

        entry = self._audio_entry()
        with patch(
            "core.transcription._recognize",
            side_effect=InvalidArgument("nope"),
        ), patch(
            "core.transcription._recognize_segmented",
            side_effect=RuntimeError("ffmpeg missing"),
        ):
            with self.assertRaises(RuntimeError):
                transcribe_entry(entry)
        entry.refresh_from_db()
        self.assertIsNone(entry.transcribed_at)

    def test_typed_body_is_not_overwritten(self):
        from unittest.mock import patch

        from .transcription import transcribe_entry

        entry = self._audio_entry(body="my note")
        with patch("core.transcription._recognize", return_value="spoken extra"):
            transcribe_entry(entry)
        entry.refresh_from_db()
        self.assertEqual(entry.body, "my note")
        self.assertEqual(entry.transcript, "spoken extra")

    def test_no_speech_is_recorded_not_retried(self):
        from unittest.mock import patch

        from .transcription import transcribe_entry

        entry = self._audio_entry()
        with patch("core.transcription._recognize", return_value=""):
            transcribe_entry(entry)
        entry.refresh_from_db()
        self.assertEqual(entry.transcript, "")
        self.assertIsNotNone(entry.transcribed_at)
        pending = Entry.objects.exclude(audio_key="").filter(
            transcribed_at__isnull=True
        )
        self.assertNotIn(entry, pending)

    def test_text_only_entry_returns_none(self):
        from .transcription import transcribe_entry

        entry = Entry.objects.create(
            user=self.user, raw="x", body="x", log_date=datetime.date(2026, 8, 28)
        )
        self.assertIsNone(transcribe_entry(entry))

    def test_sweep_transcribes_then_enriches_same_pass(self):
        from io import StringIO
        from unittest.mock import patch

        from django.core.management import call_command

        entry = self._audio_entry()
        out = StringIO()
        with patch(
            "core.transcription._recognize", return_value="a spoken project idea"
        ), patch("core.enrichment._call_model", return_value=result_fixture()):
            call_command("sweep", stdout=out)
        entry.refresh_from_db()
        self.assertEqual(entry.body, "a spoken project idea")
        self.assertEqual(entry.enrichments.count(), 1)
        self.assertIn("transcribed 1", out.getvalue())
        self.assertIn("enriched 1", out.getvalue())

    def test_post_with_audio_survives_transcription_failure(self):
        from unittest.mock import patch

        self.client.force_login(self.user)
        clip = SimpleUploadedFile("r.webm", b"bytes", content_type="audio/webm")
        with patch(
            "core.transcription._recognize", side_effect=RuntimeError("stt down")
        ), patch("core.enrichment._call_model", side_effect=RuntimeError("api down")):
            response = self.client.post(
                reverse("index"), {"text": "", "tz": "UTC", "audio": clip}
            )
        entry = self.user.entries.get()
        self.assertRedirects(response, f"/?new={entry.pk}")
        self.assertIsNone(entry.transcribed_at)


class PwaTests(TestCase):
    def test_manifest_is_linked(self):
        response = self.client.get("/accounts/login/")
        self.assertContains(response, 'rel="manifest"')
        self.assertContains(response, "apple-touch-icon")

    def test_service_worker_served_at_root_scope(self):
        response = self.client.get("/sw.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/javascript")
        self.assertIn("navigate", response.content.decode())

    def test_loading_shell_is_public_and_branded(self):
        response = self.client.get(reverse("loading"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "loading-spinner")
        self.assertContains(response, "M38 34 V84")

    def test_service_worker_precaches_the_loading_shell(self):
        response = self.client.get("/sw.js")
        content = response.content.decode()
        self.assertIn('"/loading"', content)
        self.assertIn("COLD_MS", content)

    def test_offline_page_is_public(self):
        response = self.client.get(reverse("offline"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The log will keep.")


class EntryDetailTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.entry = Entry.objects.create(
            user=self.user,
            raw="A permalinked thought.",
            body="A permalinked thought.",
            log_date=datetime.date(2026, 8, 28),
        )

    def test_owner_sees_their_entry(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("entry_detail", args=[self.entry.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A permalinked thought.")

    def test_stranger_gets_404(self):
        stranger = make_user("stranger@example.com")
        self.client.force_login(stranger)
        response = self.client.get(reverse("entry_detail", args=[self.entry.pk]))
        self.assertEqual(response.status_code, 404)

    def test_anonymous_is_sent_to_sign_in(self):
        response = self.client.get(reverse("entry_detail", args=[self.entry.pk]))
        self.assertEqual(response.status_code, 302)

    def test_index_links_each_entry(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("index"))
        self.assertContains(
            response, reverse("entry_detail", args=[self.entry.pk])
        )

    def test_menu_offers_star_and_copy_link(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("index"))
        self.assertContains(response, ">Star</button>")
        self.assertContains(response, "data-copy-link")

    def test_account_menu_shows_revision(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("index"))
        self.assertContains(response, 'class="who-version"')

    def test_templates_never_hardcode_the_script_path(self):
        # The unhashed /static/app.js fossilized in service worker
        # caches once; never again. Templates must use {% static %}.
        from pathlib import Path

        from django.conf import settings

        for name in ["index.html", "entry.html", "base.html"]:
            source = (Path(settings.BASE_DIR) / "templates" / name).read_text()
            self.assertNotIn('src="/static/', source, name)

    def test_star_toggles_and_shows_mark(self):
        self.client.force_login(self.user)
        self.client.post(reverse("entry_star", args=[self.entry.pk]))
        self.entry.refresh_from_db()
        self.assertTrue(self.entry.starred)
        response = self.client.get(reverse("index"))
        self.assertContains(response, "star-mark")
        self.assertContains(response, ">Unstar</button>")
        self.client.post(reverse("entry_star", args=[self.entry.pk]))
        self.entry.refresh_from_db()
        self.assertFalse(self.entry.starred)

    def test_stranger_cannot_star(self):
        stranger = make_user("stranger@example.com")
        self.client.force_login(stranger)
        self.client.post(reverse("entry_star", args=[self.entry.pk]))
        self.entry.refresh_from_db()
        self.assertFalse(self.entry.starred)

    def test_star_requires_post(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("entry_star", args=[self.entry.pk]))
        self.assertEqual(response.status_code, 405)


class SearchTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.birdhouse = Entry.objects.create(
            user=self.user,
            raw="The birdhouse gains a roof today.",
            body="The birdhouse gains a roof today.",
            log_date=datetime.date(2026, 8, 27),
        )
        self.groceries = Entry.objects.create(
            user=self.user,
            raw="Groceries and rain.",
            body="Groceries and rain.",
            log_date=datetime.date(2026, 8, 28),
        )
        self.idea_tag = Tag.objects.create(
            user=self.user, slug="project_idea", kind=Tag.WATCHED
        )
        self.wood_tag = Tag.objects.create(user=self.user, slug="woodworking")
        EntryTag.objects.create(entry=self.birdhouse, tag=self.idea_tag)
        EntryTag.objects.create(entry=self.birdhouse, tag=self.wood_tag)

    def test_parse_query_splits_tags_from_text(self):
        from .search import parse_query

        text, tags, starred = parse_query("birdhouse #project_idea roof #Birds")
        self.assertEqual(text, "birdhouse roof")
        self.assertEqual(tags, ["project_idea", "birds"])
        self.assertFalse(starred)

    def test_parse_query_reads_is_starred(self):
        from .search import parse_query

        text, tags, starred = parse_query("is:starred roof #birds")
        self.assertTrue(starred)
        self.assertEqual(text, "roof")
        self.assertEqual(tags, ["birds"])

    def test_starred_filter_composes(self):
        from .search import search_entries

        self.birdhouse.starred = True
        self.birdhouse.save()
        self.assertEqual(
            list(search_entries(self.user, "is:starred")), [self.birdhouse]
        )
        self.assertEqual(
            list(search_entries(self.user, "is:starred rain")), []
        )

    def test_text_search_matches_body(self):
        from .search import search_entries

        results = list(search_entries(self.user, "BIRDHOUSE"))
        self.assertEqual(results, [self.birdhouse])

    def test_tag_search(self):
        from .search import search_entries

        results = list(search_entries(self.user, "#project_idea"))
        self.assertEqual(results, [self.birdhouse])

    def test_text_and_tag_compose(self):
        from .search import search_entries

        self.assertEqual(
            list(search_entries(self.user, "roof #project_idea")), [self.birdhouse]
        )
        self.assertEqual(
            list(search_entries(self.user, "rain #project_idea")), []
        )

    def test_multiple_tags_are_anded(self):
        from .search import search_entries

        lonely = Tag.objects.create(user=self.user, slug="rain")
        EntryTag.objects.create(entry=self.groceries, tag=lonely)
        self.assertEqual(
            list(search_entries(self.user, "#project_idea #woodworking")),
            [self.birdhouse],
        )
        self.assertEqual(
            list(search_entries(self.user, "#project_idea #rain")), []
        )

    def test_search_is_scoped_to_user(self):
        from .search import search_entries

        other = make_user("other@example.com")
        Entry.objects.create(
            user=other,
            raw="Another birdhouse entirely.",
            body="Another birdhouse entirely.",
            log_date=datetime.date(2026, 8, 28),
        )
        self.assertEqual(
            list(search_entries(self.user, "birdhouse")), [self.birdhouse]
        )

    def test_view_renders_results_and_count(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("index"), {"q": "birdhouse"})
        self.assertContains(response, "1 match")
        self.assertContains(response, "The birdhouse gains a roof")
        self.assertNotContains(response, "Groceries and rain")

    def test_chips_link_into_search(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("index"))
        self.assertContains(response, 'href="/?q=%23project_idea"')

    def test_no_match_says_so(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("index"), {"q": "zeppelin"})
        self.assertContains(response, "Nothing matches.")


class SynthesisTests(TestCase):
    def setUp(self):
        from .models import Tag

        self.user = make_user()
        Tag.objects.create(user=self.user, slug="car", kind=Tag.FREE)
        self.seed = Entry.objects.create(
            user=self.user,
            raw="Check the car sticker.",
            body="I should check that the car has its city sticker.",
            log_date=datetime.date(2026, 8, 28),
        )

    def _result(self, **overrides):
        from .synthesis import AttachColor, Complete, NewTodo, SynthesisResult

        base = dict(
            new_todos=[
                NewTodo(
                    title="Confirm the car sticker",
                    summary="The city sticker may be missing.",
                    horizon="soon",
                    topic="car",
                    seed_entry_ids=[self.seed.pk],
                    items=["Look at the windshield"],
                )
            ],
            color=[],
            completions=[],
        )
        base.update(overrides)
        return SynthesisResult(**base)

    def test_synthesis_creates_proposed_todo_with_links(self):
        from unittest.mock import patch

        from .models import Todo, TodoEntry
        from .synthesis import run_synthesis

        with patch("core.synthesis._call_model", return_value=self._result()):
            run = run_synthesis(self.user)
        self.assertEqual(run.version, 1)
        todo = self.user.todos.get()
        self.assertEqual(todo.status, Todo.PROPOSED)
        self.assertEqual(todo.topic.slug, "car")
        self.assertEqual(todo.items.count(), 1)
        link = todo.todo_entries.get()
        self.assertEqual((link.entry_id, link.role), (self.seed.pk, TodoEntry.SEED))

    def test_completion_attaches_and_surfaces(self):
        from unittest.mock import patch

        from .models import Todo, TodoEntry
        from .synthesis import Complete, run_synthesis

        with patch("core.synthesis._call_model", return_value=self._result()):
            run_synthesis(self.user)
        todo = self.user.todos.get()
        todo.status = Todo.OPEN
        todo.save()
        closer = Entry.objects.create(
            user=self.user,
            raw="Sticker is on the car.",
            body="The car does indeed have the sticker.",
            log_date=datetime.date(2026, 8, 29),
        )
        result = self._result(
            new_todos=[],
            completions=[Complete(todo_id=todo.pk, entry_id=closer.pk, excerpt="does indeed have")],
        )
        with patch("core.synthesis._call_model", return_value=result):
            run = run_synthesis(self.user)
        self.assertEqual(run.version, 2)
        self.assertTrue(
            todo.todo_entries.filter(entry=closer, role=TodoEntry.COMPLETION).exists()
        )
        todo.refresh_from_db()
        self.assertEqual(todo.status, Todo.OPEN)

    def test_synthesis_skips_when_nothing_new(self):
        from unittest.mock import patch

        from .synthesis import run_synthesis

        with patch("core.synthesis._call_model", return_value=self._result()):
            run_synthesis(self.user)
        with patch("core.synthesis._call_model") as call:
            self.assertIsNone(run_synthesis(self.user))
        self.assertFalse(call.called)

    def test_topic_vocabulary_is_watched_plus_recurring(self):
        from .models import EntryTag, Tag
        from .synthesis import _topic_vocabulary

        watched = Tag.objects.create(
            user=self.user, slug="project_idea", kind=Tag.WATCHED
        )
        rare = Tag.objects.create(user=self.user, slug="one_off", kind=Tag.FREE)
        common = self.user.tags.get(slug="car")
        for i in range(3):
            entry = Entry.objects.create(
                user=self.user, raw=f"n{i}", body=f"n{i}",
                log_date=datetime.date(2026, 8, 28),
            )
            EntryTag.objects.create(entry=entry, tag=common)
        vocabulary = _topic_vocabulary(self.user)
        self.assertIn("project_idea", vocabulary)
        self.assertIn("car", vocabulary)
        self.assertNotIn("one_off", vocabulary)
        self.assertEqual(vocabulary[0], "project_idea")

    def test_retopic_reassigns_and_clears(self):
        from unittest.mock import patch

        from .models import Tag, Todo
        from .synthesis import RetopicResult, TopicFix, retopic

        car = self.user.tags.get(slug="car")
        narrow = Tag.objects.create(user=self.user, slug="brake_noise", kind=Tag.FREE)
        a = Todo.objects.create(
            user=self.user, title="Fix the brakes", status=Todo.OPEN, topic=narrow
        )
        b = Todo.objects.create(
            user=self.user, title="Mystery errand", status=Todo.OPEN, topic=narrow
        )
        result = RetopicResult(
            fixes=[
                TopicFix(todo_id=a.pk, topic="car"),
                TopicFix(todo_id=b.pk, topic=""),
            ]
        )
        with patch("core.synthesis._call_retopic", return_value=result):
            retopic(self.user)
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.topic, car)
        self.assertIsNone(b.topic)
        self.assertEqual(a.status, Todo.OPEN)

    def test_invalid_seed_ids_drop_the_proposal(self):
        from unittest.mock import patch

        from .synthesis import NewTodo, run_synthesis

        result = self._result(
            new_todos=[
                NewTodo(
                    title="Ghost", summary="", horizon="now",
                    seed_entry_ids=[99999],
                )
            ]
        )
        with patch("core.synthesis._call_model", return_value=result):
            run_synthesis(self.user)
        self.assertEqual(self.user.todos.count(), 0)


class TodoViewTests(TestCase):
    def setUp(self):
        from .models import Todo

        self.user = make_user()
        self.entry = Entry.objects.create(
            user=self.user, raw="x", body="x", log_date=datetime.date(2026, 8, 28)
        )
        self.todo = Todo.objects.create(
            user=self.user, title="Confirm the car sticker", summary="s"
        )

    def test_tabs_render_on_both_pages(self):
        self.client.force_login(self.user)
        for url in [reverse("index"), reverse("todos")]:
            response = self.client.get(url)
            self.assertContains(response, 'class="tabs"')
            self.assertContains(response, ">Todos</a>")

    def test_proposed_todo_offers_verdicts(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("todos"))
        self.assertContains(response, "Confirm the car sticker")
        self.assertContains(response, ">Accept</button>")
        self.assertContains(response, ">Dismiss</button>")

    def test_verdict_lifecycle(self):
        from .models import Todo

        self.client.force_login(self.user)
        self.client.post(reverse("todo_verdict", args=[self.todo.pk, "accept"]))
        self.todo.refresh_from_db()
        self.assertEqual(self.todo.status, Todo.OPEN)
        self.assertIsNotNone(self.todo.decided_at)
        self.client.post(reverse("todo_verdict", args=[self.todo.pk, "done"]))
        self.todo.refresh_from_db()
        self.assertEqual(self.todo.status, Todo.DONE)
        self.client.post(reverse("todo_verdict", args=[self.todo.pk, "reopen"]))
        self.todo.refresh_from_db()
        self.assertEqual(self.todo.status, Todo.OPEN)
        self.assertIsNone(self.todo.done_at)

    def test_done_never_writes_an_entry(self):
        self.client.force_login(self.user)
        before = self.user.entries.count()
        self.client.post(reverse("todo_verdict", args=[self.todo.pk, "accept"]))
        self.client.post(reverse("todo_verdict", args=[self.todo.pk, "done"]))
        self.assertEqual(self.user.entries.count(), before)

    def test_stranger_cannot_verdict(self):
        from .models import Todo

        stranger = make_user("stranger@example.com")
        self.client.force_login(stranger)
        self.client.post(reverse("todo_verdict", args=[self.todo.pk, "accept"]))
        self.todo.refresh_from_db()
        self.assertEqual(self.todo.status, Todo.PROPOSED)

    def test_item_toggle(self):
        from .models import TodoItem

        item = TodoItem.objects.create(todo=self.todo, text="look")
        self.client.force_login(self.user)
        self.client.post(reverse("todo_item_toggle", args=[item.pk]))
        item.refresh_from_db()
        self.assertTrue(item.done)

    def test_horizon_edit(self):
        from .models import Todo

        self.client.force_login(self.user)
        self.client.post(
            reverse("todo_horizon", args=[self.todo.pk]), {"horizon": "someday"}
        )
        self.todo.refresh_from_db()
        self.assertEqual(self.todo.horizon, Todo.SOMEDAY)

    def test_entry_delete_keeps_todo(self):
        from .models import TodoEntry

        TodoEntry.objects.create(todo=self.todo, entry=self.entry, role=TodoEntry.SEED)
        self.client.force_login(self.user)
        self.client.post(reverse("entry_delete", args=[self.entry.pk]))
        self.todo.refresh_from_db()
        self.assertEqual(self.todo.todo_entries.count(), 0)
        self.assertEqual(self.user.todos.count(), 1)


@override_settings(PIPELINES_INLINE_DISABLED=True)
class TodoTabFeatureTests(TestCase):
    def setUp(self):
        from .models import Todo

        self.user = make_user()
        self.todo = Todo.objects.create(
            user=self.user, title="Paint the fence", status=Todo.OPEN,
            horizon=Todo.SOON, decided_at=timezone.now(),
        )
        self.client.force_login(self.user)

    def test_create_todo_in_app(self):
        from .models import Todo

        self.client.post(
            reverse("todo_create"), {"title": "Sharpen the axe", "horizon": "now"}
        )
        todo = self.user.todos.get(title="Sharpen the axe")
        self.assertEqual(todo.status, Todo.OPEN)
        self.assertEqual(todo.horizon, Todo.NOW)
        self.assertIsNotNone(todo.decided_at)

    def test_blank_title_creates_nothing(self):
        before = self.user.todos.count()
        self.client.post(reverse("todo_create"), {"title": "  ", "horizon": "now"})
        self.assertEqual(self.user.todos.count(), before)

    def test_search_filters_todos(self):
        from .models import Todo

        Todo.objects.create(
            user=self.user, title="Buy paint", status=Todo.OPEN, horizon=Todo.SOON
        )
        response = self.client.get(reverse("todos"), {"q": "fence"})
        self.assertContains(response, "Paint the fence")
        self.assertNotContains(response, "Buy paint")

    def test_outstanding_count_renders(self):
        response = self.client.get(reverse("todos"))
        self.assertContains(response, "1 outstanding.")

    def test_someday_and_done_fold_closed_by_default(self):
        import re

        response = self.client.get(reverse("todos"))
        html = response.content.decode()
        someday = re.search(r'<details[^>]*data-fold="someday"[^>]*>', html).group(0)
        soon = re.search(r'<details[^>]*data-fold="soon"[^>]*>', html).group(0)
        done = re.search(r'<details[^>]*data-fold="done"[^>]*>', html).group(0)
        self.assertNotIn(" open", someday)
        self.assertNotIn(" open", done)
        self.assertIn(" open", soon)

    def test_todo_note_becomes_linked_entry(self):
        from .models import TodoEntry

        self.client.post(
            reverse("todo_note", args=[self.todo.pk]),
            {"text": "Cedar, not pine.", "tz": "America/New_York",
             "log_date": "2026-09-01"},
        )
        entry = self.user.entries.get()
        self.assertEqual(entry.body, "Cedar, not pine.")
        link = self.todo.todo_entries.get()
        self.assertEqual(link.entry, entry)
        self.assertEqual(link.role, TodoEntry.COLOR)
        self.assertEqual(link.source, TodoEntry.USER)
        response = self.client.get(reverse("todos"))
        self.assertContains(response, "Cedar, not pine.")
        response = self.client.get(reverse("index"))
        self.assertContains(response, "Cedar, not pine.")

    def test_blank_note_creates_nothing(self):
        self.client.post(reverse("todo_note", args=[self.todo.pk]), {"text": " "})
        self.assertEqual(self.user.entries.count(), 0)

    def test_plus_adds_line_item_and_positions_it(self):
        from .models import TodoItem

        TodoItem.objects.create(todo=self.todo, text="first", position=0)
        self.client.post(
            reverse("todo_item_add", args=[self.todo.pk]), {"text": "second"}
        )
        items = list(self.todo.items.values_list("text", "position"))
        self.assertEqual(items, [("first", 0), ("second", 1)])

    def test_plus_creates_the_list_when_none_exists(self):
        self.client.post(
            reverse("todo_item_add", args=[self.todo.pk]), {"text": "born first"}
        )
        item = self.todo.items.get()
        self.assertEqual((item.text, item.position, item.done), ("born first", 0, False))

    def test_blank_item_ignored_and_stranger_blocked(self):
        self.client.post(reverse("todo_item_add", args=[self.todo.pk]), {"text": " "})
        self.assertEqual(self.todo.items.count(), 0)
        stranger = make_user("stranger@example.com")
        self.client.force_login(stranger)
        self.client.post(
            reverse("todo_item_add", args=[self.todo.pk]), {"text": "intrusion"}
        )
        self.assertEqual(self.todo.items.count(), 0)

    def test_stranger_cannot_note_anothers_todo(self):
        stranger = make_user("stranger@example.com")
        self.client.force_login(stranger)
        self.client.post(
            reverse("todo_note", args=[self.todo.pk]), {"text": "mine now"}
        )
        self.assertEqual(self.todo.todo_entries.count(), 0)


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
