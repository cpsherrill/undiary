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
        self.assertRedirects(response, reverse("index"))
        self.assertTrue(self.user.entries.filter(raw="still saved").exists())

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
        self.assertRedirects(response, reverse("index"))
        entry = self.user.entries.get()
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

        text, tags = parse_query("birdhouse #project_idea roof #Birds")
        self.assertEqual(text, "birdhouse roof")
        self.assertEqual(tags, ["project_idea", "birds"])

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
