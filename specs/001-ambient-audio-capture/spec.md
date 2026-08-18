# Feature Specification: Ambient Audio Capture Sessions

**Feature Branch**: `001-ambient-audio-capture`

**Created**: 2026-07-27

**Status**: Draft

**Input**: User description: "Build the feature described in spec-001-ambient-audio-capture.md — the foundation of the ambient recorder: start a recording session that captures everything audible in a meeting (user's microphone and the machine's audio output) and persist it durably to local storage with session metadata. Capture and persistence only; no transcription or analysis."

## Clarifications

### Session 2026-07-27

- Q: When a capture device disappears mid-session, what should happen? → A: Continue with the surviving source; the lost source ends at the point of loss and the session records a device-loss event (no auto-reconnect in v1).
- Q: Can a session start when one of the two capture sources is unavailable? → A: No — both sources (microphone and system audio) are strictly required; start is always refused if either is missing.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Start and stop a recording session (Priority: P1)

Before a meeting, the user starts a session (giving it an optional title).
During the meeting, both sides of the conversation are captured — the user's
microphone and the audio the machine plays (remote participants). Afterwards,
the user stops the session and can see it listed with its duration, size, and
timestamps.

**Why this priority**: This is the product's foundation. Without reliable
capture and persistence, nothing downstream (transcription, assistant,
search) matters.

**Independent Test**: Start a session, play known audio through the speakers
while speaking into the microphone for a few minutes, stop the session.
Verify the session appears in the list with correct metadata and that both
captured sources contain the expected audio, separably.

**Acceptance Scenarios**:

1. **Given** the recorder is running and devices are available, **When** the
   user starts a session with a title, **Then** capture begins on both
   sources and the session is reported as active with its start timestamp.
2. **Given** an active session, **When** the user stops it, **Then** the
   session is finalised as completed and lists duration, size on disk, and
   start/end timestamps.
3. **Given** a completed session, **When** the user inspects it, **Then** the
   microphone audio and system audio are stored separately and each is
   individually intact.

---

### User Story 2 - Survive a mid-meeting failure (Priority: P2)

The recorder process is killed 40 minutes into an hour-long meeting. When the
user restarts it, all audio up to the failure point is intact and the session
is marked as interrupted — not lost, not corrupted.

**Why this priority**: Losing a meeting recording is the worst failure mode
this system has (constitution Principle VII). Durability is what makes the
recorder trustworthy enough to rely on.

**Independent Test**: Start a session, capture for several minutes, terminate
the recorder process ungracefully, restart it. Verify the session is
finalised as interrupted and all audio except at most the final 10 seconds is
playable in an external tool.

**Acceptance Scenarios**:

1. **Given** an active session, **When** the recorder process is terminated
   ungracefully, **Then** no more than the most recent 10 seconds of audio
   per source is lost.
2. **Given** a session interrupted by process death, **When** the recorder
   restarts, **Then** it reconciles on-disk audio with session metadata and
   marks the session interrupted without user intervention.
3. **Given** an active session, **When** the UI/API client disconnects,
   **Then** recording continues unaffected — the session belongs to the
   recorder, not the client connection.

---

### User Story 3 - Device sanity before it matters (Priority: P3)

The user starts a session with a headset unplugged. The system reports which
capture sources are available and which are missing *before* recording begins
— not as a silent zero-byte recording discovered later.

**Why this priority**: A recording that silently captured nothing is
indistinguishable from data loss. Pre-flight checks convert the failure into
an immediate, actionable error.

**Independent Test**: Disable or unplug a capture device, attempt to start a
session, and verify a clear error names the missing device and no session
starts. Re-enable the device and verify readiness is reported as good.

**Acceptance Scenarios**:

1. **Given** either capture device (microphone or system audio) is missing,
   **When** the user attempts to start a session, **Then** the attempt is
   refused with an error naming the missing device(s), and no partial
   session is created — both sources are strictly required to start.
2. **Given** the recorder is idle, **When** the user asks for device
   readiness, **Then** each capture source is reported as present, missing,
   or default-changed.
3. **Given** free disk space is below the configured threshold, **When** the
   user attempts to start a session, **Then** the attempt is refused with a
   clear disk-space error.

---

### User Story 4 - Ambient readiness (Priority: P4)

The user leaves the recorder running between meetings. Starting a new session
takes effect within 2 seconds and does not require restarting the
application.

**Why this priority**: The recorder is meant to be ambient — always ready.
Fast, repeatable session starts remove the friction that would otherwise
cause missed meeting openings.

**Independent Test**: With the recorder already running, start and stop
several sessions in sequence, measuring the time from start request to
capture actually beginning.

**Acceptance Scenarios**:

1. **Given** the recorder has been idle for hours, **When** the user starts a
   session, **Then** capture begins within 2 seconds of the request.
2. **Given** a session has just been stopped, **When** the user starts a new
   one, **Then** it starts cleanly without restarting the recorder.

---

### Edge Cases

- A capture device disappears mid-session (headset unplugged during a
  meeting): the session continues with the surviving source; the lost
  source ends at the point of loss and a device-loss event is recorded in
  session metadata (no auto-reconnect in v1). Already-persisted audio is
  never corrupted, and nothing is silently written as empty audio.
- The default output device changes mid-session (user switches to different
  speakers): readiness reporting must surface default-changed; in-session,
  the change is treated as loss of the system-audio source (capture of the
  original device ends; no automatic re-attachment to the new default in v1).
- Disk fills up during an active session: capture must stop safely and
  finalise the session rather than corrupt existing chunks.
- A start request arrives while a session is already active: refused —
  exactly one session may be active at a time (see Assumptions).
- The recorder is restarted while no session was active: startup
  reconciliation finds nothing to repair and completes silently.
- System clock changes mid-session: durations derive from captured audio
  length, not wall-clock subtraction.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST capture microphone input and system/loopback
  audio concurrently for the duration of a session.
- **FR-002**: The system MUST persist audio incrementally in chunks of 10
  seconds, such that an ungraceful termination loses no more than the most
  recent chunk per source (max data-loss window: 10 seconds).
- **FR-003**: The system MUST store the two capture sources such that they
  remain separable downstream (mic vs. remote audio), preserving a cheap
  speaker-attribution signal for later transcription features.
- **FR-004**: The system MUST record session metadata: id, optional title,
  start/end timestamps, source device identities, sample rate/format, status
  (active | completed | interrupted), and file references.
- **FR-005**: The system MUST enumerate available capture devices and report
  readiness (present / missing / default-changed) before a session starts.
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
- **FR-011**: If a capture source's device is lost mid-session, the system
  MUST continue capturing the surviving source; the lost source ends at the
  point of loss, a device-loss event is recorded in session metadata, and no
  automatic re-attachment is attempted in v1.
- **FR-012**: A session MUST NOT start unless both capture sources
  (microphone and system audio) are available; a start attempt with either
  missing is refused with an error naming the missing device(s). There is no
  single-source override in v1.

### Non-Functional Requirements

- **NFR-001**: Steady-state capture overhead small enough to coexist with a
  video call: < 5% CPU, no GPU usage, < 200 MB RAM.
- **NFR-002**: Audio is persisted at 16 kHz mono, 16-bit PCM, per source —
  the standard operating point for speech-to-text models generally (not a
  provider-specific choice), directly consumable by any STT ingest without
  conversion. Speech intelligibility lives below 8 kHz; higher rates add disk
  cost without transcription benefit.
- **NFR-003**: A 2-hour session must not exceed ~500 MB on disk (two sources
  at 16 kHz mono 16-bit is ~460 MB uncompressed; budget allows metadata and
  chunk overhead).

### Key Entities

- **Session**: A bounded recording with metadata (id, optional title,
  timestamps, status: active | completed | interrupted) and references to its
  captured audio; owns one or more capture sources.
- **CaptureSource**: One input (microphone or system audio) with device
  identity and format; belongs to a session.
- **AudioChunk**: An incrementally persisted segment belonging to a session
  and source; ordered, contiguous, individually valid.

## Out of Scope *(this feature)*

- Transcription, diarisation, or any ML inference.
- The interactive assistant / UI beyond what's needed to exercise the API.
- Automatic meeting detection (auto-start on call join).
- Multi-machine or cloud sync of any kind.
- Audio playback.
- Per-application audio capture (default output device only in v1).
- Storage retention / auto-cleanup (deferred to a later library-management
  feature; FR-007's disk-space check is the only storage guard in v1).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A 60-minute simulated meeting (microphone + system audio) is
  captured with both sources intact and separable, within the size budget
  (≤ 250 MB for one hour, two sources).
- **SC-002**: Ungraceful process termination during recording, followed by
  restart, yields a session finalised as interrupted with all audio except
  at most the final 10 seconds per source playable in an external tool.
- **SC-003**: Starting a session with a missing device produces a clear,
  typed error naming the device — never a silent partial recording — in
  100% of attempts.
- **SC-004**: With the recorder already running, a session start takes
  effect within 2 seconds of the request.
- **SC-005**: All API payloads round-trip through their declared schemas;
  contract tests pass.
- **SC-006**: Steady-state recording coexists with a live video call without
  user-perceptible impact (< 5% CPU, no GPU usage, < 200 MB RAM).

## Assumptions

- Exactly one session may be active at a time; a start request during an
  active session is refused. (Meetings don't overlap on one machine; this
  keeps the lifecycle simple in v1.)
- "Create" and "start" (FR-006) are a single atomic operation: a session
  only comes into existence once preflight passes and capture begins; a
  failed preflight creates nothing. There is no dormant created-but-not-
  started state.
- The recorder runs as a single long-lived local process on the user's
  Windows 11 machine; the user is its only operator, and no authentication
  is required for the local API in v1.
- "System audio" means whatever the default output device plays; capturing
  it captures all machine audio during the session (including non-meeting
  sounds), which is acceptable for an ambient recorder.
- Storage is the local disk; the configurable free-space threshold has a
  sensible default chosen at planning time.
- Device-rate capture with conversion on write is permitted as an
  implementation choice; the persisted artifact is 16 kHz mono 16-bit PCM
  per NFR-002.

## Decision Log

- 2026-07-26: Chunk duration fixed at 10 s (FR-002).
- 2026-07-26: System audio = default output device only for v1 (FR-005).
- 2026-07-26: Retention deferred to a later feature; disk-space threshold
  check (FR-007) is the only v1 storage guard.
- 2026-07-26: Capture format = 16 kHz mono 16-bit PCM per source (NFR-002).
  YAGNI: 16 kHz is the universal STT operating point; higher rates only
  matter for human-facing playback, which is out of scope. Revisit only if a
  concrete playback/fidelity requirement appears.
- 2026-07-27: Single active session at a time in v1 (see Assumptions).
