"""Transcripts for audio entries via Speech-to-Text v2. Derived and
re-runnable, since the audio is kept. "No speech detected" is a normal
outcome recorded by transcribed_at, not an error.

Short clips go through synchronous recognition; anything past its
limits falls back to batch recognition reading straight from GCS.
"""

import logging
import os

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone

logger = logging.getLogger(__name__)


def transcribe_entry(entry):
    """Run one transcription attempt and record it. Returns the entry,
    or None when there is no audio to read."""
    if not entry.audio_key:
        return None

    with default_storage.open(entry.audio_key) as f:
        data = f.read()

    try:
        text = _recognize(data)
    except _too_long_errors() as exc:
        if not settings.GS_BUCKET_NAME:
            raise
        logger.info("sync recognition declined (%s); using batch", exc)
        text = _batch_recognize(f"gs://{settings.GS_BUCKET_NAME}/{entry.audio_key}")

    entry.transcript = text
    entry.transcribed_at = timezone.now()
    if text and not entry.body:
        entry.body = text
    entry.save(update_fields=["transcript", "transcribed_at", "body", "edited_at"])
    return entry


def transcribe_quietly(entry):
    """Best-effort inline attempt after a save; failures wait for the
    sweep instead of breaking the request."""
    try:
        transcribe_entry(entry)
    except Exception:
        logger.exception("inline transcription failed for entry %s", entry.pk)


# ---- Speech-to-Text v2 plumbing --------------------------------------


def _too_long_errors():
    from google.api_core.exceptions import InvalidArgument

    return InvalidArgument


def _project_id():
    explicit = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    if explicit:
        return explicit
    import google.auth

    return google.auth.default()[1]


def _recognizer():
    return f"projects/{_project_id()}/locations/global/recognizers/_"


def _config():
    from google.cloud.speech_v2.types import cloud_speech

    return cloud_speech.RecognitionConfig(
        auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
        language_codes=[settings.SPEECH_LANGUAGE],
        model="long",
    )


def _join(results):
    return " ".join(
        r.alternatives[0].transcript.strip() for r in results if r.alternatives
    ).strip()


def _recognize(data):
    from google.cloud.speech_v2 import SpeechClient
    from google.cloud.speech_v2.types import cloud_speech

    client = SpeechClient()
    response = client.recognize(
        request=cloud_speech.RecognizeRequest(
            recognizer=_recognizer(), config=_config(), content=data
        ),
        timeout=60,
    )
    return _join(response.results)


def _batch_recognize(gcs_uri):
    from google.cloud.speech_v2 import SpeechClient
    from google.cloud.speech_v2.types import cloud_speech

    client = SpeechClient()
    operation = client.batch_recognize(
        request=cloud_speech.BatchRecognizeRequest(
            recognizer=_recognizer(),
            config=_config(),
            files=[cloud_speech.BatchRecognizeFileMetadata(uri=gcs_uri)],
            recognition_output_config=cloud_speech.RecognitionOutputConfig(
                inline_response_config=cloud_speech.InlineOutputConfig()
            ),
        )
    )
    result = operation.result(timeout=600)
    file_result = next(iter(result.results.values()))
    return _join(file_result.transcript.results)
