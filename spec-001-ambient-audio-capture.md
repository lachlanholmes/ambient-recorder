# Feature Spec: 001 — Ambient Audio Capture Sessions

<!-- Paste-ready seed for /speckit.specify. Deliberately implementation-free:
     no WASAPI, no library names, no endpoints — that's plan.md territory.
     [NEEDS CLARIFICATION] markers are decisions to make before /speckit.plan. -->

## What & Why

The foundation of the ambient recorder: the ability to start a recording
session that captures everything audible in a meeting — both the user's
microphone and the audio produced by the machine (remote participants in a
call) — and persist it durably to local storage with session metadata.

Without reliable capture, nothing downstream (transcription, assistant,
search) matters. This feature delivers capture and persistence only; it does
not transcribe, summarise, or analyse.

## User Scenarios

1. **Start/stop a session.** Before a meeting, the user starts a session
   (giving it an optional title). During the meeting, both sides of the
   conversation are captured. Afterwards, the user stops the session and can
   see it listed with its duration, size, and timestamps.

2. **Survive a mid-meeting failure.** The recorder process is killed 40
   minutes into an hour-long meeting. When the user restarts it, all audio up
   to the failure point is intact and the session is marked as interrupted,
   not lost or corrupted.

3. **Device sanity before it matters.** The user starts a session with a
   headset unplugged. The system reports which capture sources are available
   and which are missing *before* recording begins — not as a silent
   zero-byte recording discovered later.

4. **Ambient readiness.** The user leaves the recorder running between
   meetings. Starting a new session takes effect within 2 seconds and does
   not require restarting the application.

## Functional Requirements

- **FR-001**: The system MUST capture microphone input and system/loopback
  audio concurrently for the duration of a session.
- **FR-002**: The system MUST persist audio incrementally in chunks of 10
  seconds, such that an ungraceful termination loses no more than the most
  recent chunk (max data-loss window: 10 seconds).
- **FR-003**: The system MUST store the two capture sources such that they
  remain separable downstream (mic vs. remote audio), to preserve a cheap
  speaker-attribution signal for later transcription features.
- **FR-004**: The system MUST record session metadata: id, optional title,
  start/end timestamps, source device identities, sample rate/format, status
  (active | completed | interrupted), and file references.
- **FR-005**: The system MUST enumerate available capture devices and report
  readiness (present/missing/default-changed) before a session starts.
  System-audio capture targets the default output device only in v1;
  per-application capture is explicitly out of scope.
- **FR-006**: The system MUST expose session lifecycle (create, start, stop,
  list, inspect) via a local API consumable by the future web UI, with typed
  request/response schemas.
- **FR-007**: The system MUST validate free disk space at session start and
  refuse to start below a configurable threshold.
- **FR-008**: On restart after an interruption, the system MUST reconcile
  on-disk chunks with metadata and finalise the session as interrupted
  without user intervention.
- **FR-009**: Recording MUST continue if the UI/API client disconnects; the
  session belongs to the recorder process, not the client connection.
- **FR-010**: The system MUST NOT transmit audio or derived data off the
  local machine (constitution Principle I).

## Non-Functional Requirements

- **NFR-001**: Steady-state capture overhead small enough to coexist with a
  video call: < 5% CPU, no GPU usage, < 200 MB RAM.
- **NFR-002**: Audio is captured at 16 kHz mono, 16-bit PCM, per source —
  the standard operating point for STT models generally (not a
  provider-specific choice), directly consumable by any STT ingest without
  conversion. Speech intelligibility lives below 8 kHz; higher rates add
  disk cost without transcription benefit.
- **NFR-003**: A 2-hour session must not exceed ~500 MB on disk (two sources
  at 16 kHz mono 16-bit is ~460 MB uncompressed; budget allows metadata and
  chunk overhead).

## Key Entities

- **Session** — a bounded recording with metadata and status lifecycle.
- **CaptureSource** — one input (microphone or system audio) with device
  identity and format; a session has one or more.
- **AudioChunk** — an incrementally persisted segment belonging to a session
  and source; ordered, contiguous, individually valid.

## Out of Scope (this feature)

- Transcription, diarisation, or any ML inference.
- The interactive assistant / UI beyond what's needed to exercise the API.
- Automatic meeting detection (auto-start on call join).
- Multi-machine or cloud sync of any kind.
- Audio playback.
- Per-application audio capture (default output device only in v1).
- Storage retention / auto-cleanup (deferred to a later library-management
  feature; FR-007's disk-space check is the only storage guard in v1).

## Success Criteria

- A 60-minute simulated meeting (mic + system audio) is captured with both
  sources intact, separable, and within the size budget.
- Kill -9 during recording → restart → session finalised as interrupted with
  all-but-last-chunk audio playable in an external tool.
- Starting a session with a missing device produces a clear, typed error
  naming the device — never a silent partial recording.
- All API payloads round-trip through their schemas; contract tests pass.

## Open Questions

None — spec is plan-ready.

## Decision Log

- 2026-07-26: Chunk duration fixed at 10 s (FR-002).
- 2026-07-26: System audio = default output device only for v1 (FR-005).
- 2026-07-26: Retention deferred to a later feature; disk-space threshold
  check (FR-007) is the only v1 storage guard.
- 2026-07-26: Capture format = 16 kHz mono 16-bit PCM per source (NFR-002).
  YAGNI: 16 kHz is the universal STT operating point; higher rates only
  matter for human-facing playback, which is out of scope. Revisit only if
  a concrete playback/fidelity requirement appears. Note: device-rate
  capture (typically 48 kHz) with resample-on-write is an implementation
  detail plan.md may choose; the persisted artifact is 16 kHz mono.
