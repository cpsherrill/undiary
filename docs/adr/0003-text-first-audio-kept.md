# ADR 0003: text first, audio kept

Date: 2026-08-28. Status: accepted.

## Context

The original sketch was voice-first: record in the browser, transcribe
server-side, discard audio after a good transcript. Two facts changed
it. Dictation tools (Wispr Flow among them) already turn speech into
edited text client-side, with a human in the loop before submission.
And a recording is not always speech: a hummed tune with a paired note
should be one entry.

## Decision

The text box is the front door. Submitted text arrives already edited;
the app neither knows nor cares how it was produced. A record button
optionally attaches audio, and an entry may be text, audio, or both,
never neither.

Audio is kept permanently. Discard-after-transcription was designed for
audio as a delivery mechanism for words; once audio can be the content,
a music clip run through a speech model yields confident garbage, and
discard-on-success would destroy the only capture. Volume on this path
is low, so storage is pennies.

Transcription is therefore derived: attempted on every audio,
re-runnable as models improve, with "no speech detected" as a normal
outcome.

## Consequences

Raw text and audio are immutable capture; the transcript joins the
derived layer; body stays the editable display copy. A transcription
failure holds the audio and surfaces a pending state rather than losing
words.
