"""Transport-agnostic application errors; api/errors.py maps them to HTTP."""

from __future__ import annotations

from ambient_recorder.models.session import SourceKind


class DeviceMissingError(Exception):
    def __init__(self, missing: list[SourceKind]):
        self.missing = missing
        names = ", ".join(k.value for k in missing)
        super().__init__(f"Required capture device is missing: {names}")


class DiskLowError(Exception):
    def __init__(self, free_mb: int, required_mb: int):
        self.free_mb = free_mb
        self.required_mb = required_mb
        super().__init__(f"Free disk space too low: {free_mb} MB free, {required_mb} MB required")


class SessionNotFoundError(Exception):
    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"Session not found: {session_id}")


class SessionNotActiveError(Exception):
    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"Session is not active: {session_id}")


# feature 002


class TranscriptNotFoundError(Exception):
    def __init__(self, ref: str):
        self.ref = ref
        super().__init__(f"No transcript for: {ref}")


class TranscriptionNotReadyError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Transcription is not ready: {reason}")


class SessionStillActiveError(Exception):
    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"Session is still recording (live mode owns it): {session_id}")


class TranscriptionAlreadyRunningError(Exception):
    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"An on-demand transcription is already queued/running: {session_id}")


# feature 003


class AssistantNotReadyError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Assistant is not ready: {reason}")


class TranscriptNotFinalError(Exception):
    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(
            f"Session has no final transcript to summarise (still active, live, "
            f"or never transcribed): {session_id}"
        )


class SummaryNotFoundError(Exception):
    def __init__(self, ref: str):
        self.ref = ref
        super().__init__(f"No summary for: {ref}")


class ConversationNotFoundError(Exception):
    def __init__(self, cid: str):
        self.cid = cid
        super().__init__(f"Conversation not found: {cid}")


class TurnNotFoundError(Exception):
    def __init__(self, ref: str):
        self.ref = ref
        super().__init__(f"Turn not found: {ref}")
