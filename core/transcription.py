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

    phrases = list(entry.user.lexicon_terms.all())

    try:
        text = _recognize(data, phrases)
    except _sync_declined_errors() as exc:
        # Too long or an undecodable container: transcode to mono FLAC,
        # split under the sync limit, and recognize the pieces.
        logger.info("sync recognition declined (%s); segmenting", exc)
        text = _recognize_segmented(data, phrases)

    # On a re-hear, the display copy follows the transcript only when
    # it was never anything else: empty, or exactly the old transcript
    # of an audio-only entry. A user's edit outranks better ears.
    old_transcript = entry.transcript
    entry.transcript = text
    entry.transcribed_at = timezone.now()
    if text and (
        not entry.body or (not entry.raw and entry.body == old_transcript)
    ):
        entry.body = text
    entry.save(update_fields=["transcript", "transcribed_at", "body", "edited_at"])
    return entry


def transcribe_quietly(entry):
    """Best-effort inline attempt after a save; failures wait for the
    sweep instead of breaking the request."""
    if settings.PIPELINES_INLINE_DISABLED:
        return
    try:
        transcribe_entry(entry)
    except Exception:
        logger.exception("inline transcription failed for entry %s", entry.pk)


# ---- Speech-to-Text v2 plumbing --------------------------------------


def _sync_declined_errors():
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


def _config(phrases=None):
    from google.cloud.speech_v2.types import cloud_speech

    adaptation = None
    if phrases:
        adaptation = cloud_speech.SpeechAdaptation(
            phrase_sets=[
                cloud_speech.SpeechAdaptation.AdaptationPhraseSet(
                    inline_phrase_set=cloud_speech.PhraseSet(
                        phrases=[
                            cloud_speech.PhraseSet.Phrase(
                                value=term.phrase, boost=term.boost
                            )
                            for term in phrases
                        ]
                    )
                )
            ]
        )
    return cloud_speech.RecognitionConfig(
        auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
        language_codes=[settings.SPEECH_LANGUAGE],
        model="long",
        adaptation=adaptation,
    )


def _join(results):
    return " ".join(
        r.alternatives[0].transcript.strip() for r in results if r.alternatives
    ).strip()


def _recognize(data, phrases=None):
    from google.cloud.speech_v2 import SpeechClient
    from google.cloud.speech_v2.types import cloud_speech

    client = SpeechClient()
    response = client.recognize(
        request=cloud_speech.RecognizeRequest(
            recognizer=_recognizer(), config=_config(phrases), content=data
        ),
        timeout=60,
    )
    return _join(response.results)


def _recognize_segmented(data, phrases=None):
    """ffmpeg decodes anything, so anything becomes sub-limit mono
    FLAC segments; each is recognized with our own credentials. No
    service agents, no swallowed per-file errors."""
    import glob
    import pathlib
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        src = pathlib.Path(td) / "src.audio"
        src.write_bytes(data)
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-i", str(src),
                "-ac", "1", "-ar", "16000",
                "-f", "segment", "-segment_time", "55", "-y",
                str(pathlib.Path(td) / "seg%03d.flac"),
            ],
            check=True,
            capture_output=True,
        )
        segments = sorted(glob.glob(str(pathlib.Path(td) / "seg*.flac")))
        if not segments:
            raise RuntimeError("ffmpeg produced no segments")
        parts = [
            _recognize(pathlib.Path(seg).read_bytes(), phrases)
            for seg in segments
        ]
    return " ".join(p for p in parts if p).strip()
