# Feature Specification: Local Transcription

**Feature Branch**: `002-local-transcription`

**Created**: 2026-08-18

**Status**: Draft

**Input**: User description: "Transcription (feature 002, from docs/backlog.md): local speech-to-text over the separable per-source session recordings, producing time-aligned, speaker-attributed transcripts. The mic/system split from feature 001 exists precisely to give attribution a cheap signal. Field note: laptop speakers bleed into the mic at ~¼–½ volume, so attribution must treat 'louder on which track' as the signal, not mere presence. Everything runs on-device (constitution Principle I)."

## Clarifications

### Session 2026-08-18

- Q: When does transcription run — on-demand, automatically on session completion, or live during recording? → A: **Live during recording**, with streaming partial transcripts; the transcript grows while the meeting is happening. Completed/interrupted/legacy sessions are additionally transcribable on demand (US3).
- Q: What happens to the live transcript when lag exceeds the NFR-001 bound? → A: **Never skip audio** — the transcript stays complete but late; lag grows, is reported, and shrinks when load eases; finalisation waits for the backlog to drain (may exceed SC-007's 30 s under sustained overload, visibly, in `finalising`).
- Q: When an on-demand pass runs on a session that already has a live transcript, what happens to the live one? → A: **Supersede but keep** — the on-demand result becomes the session's current transcript; the prior live transcript is retained (readable on request, marked superseded) but not returned by default. Nothing is destroyed.
- Q: Which GPU co-residents must the VRAM plan account for? → A: **Reserve for co-residency** — STT must fit alongside a quantised 3–4B LLM per the constitution's default assumption (~3–4 GB reserved for the future assistant), so that feature needs no re-planning.
- Q: What does a consumer that connects or reconnects mid-session receive on the live stream? → A: **Snapshot + tail** — the client fetches the transcript so far, then subscribes from a cursor (the last segment it saw); the stream delivers exactly the segments after that cursor, so reconnects are lossless and duplicate-free.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See what is being said, as it is said (Priority: P1)

While a meeting is being recorded, the user can watch the transcript grow:
each utterance appears shortly after it is spoken, with a timestamp and an
attribution of whether it came from the user (microphone) or from the
other participants (system audio). When the session stops, the transcript
is finalised and remains available afterwards.

**Why this priority**: Live transcription is the product's first real
payoff and the foundation of the assistant vision — a running record the
user (and future features) can consult *during* the meeting, not just
after. Recordings alone are opaque.

**Independent Test**: Start a session, speak into the mic while known
audio plays, watch new segments arrive while still recording; stop, and
verify the finalised transcript contains both sides' words, in order,
correctly attributed.

**Acceptance Scenarios**:

1. **Given** an active session with speech occurring, **When** the user
   observes the live transcript, **Then** each spoken utterance appears
   as a segment (start/end time, text, `me`/`them` attribution) within
   the latency bound (SC-002, ≤ 15 s p95) after it ended.
2. **Given** an active session, **When** the user requests the transcript
   so far, **Then** they receive every segment produced to that point in
   chronological order, plus an indication that it is still growing.
3. **Given** a session that has just been stopped, **When** the user
   requests its transcript, **Then** the last spoken audio is included and
   the transcript is marked final.
4. **Given** a finalised transcript, **When** the user retrieves it later
   (including after a recorder restart), **Then** the same transcript is
   returned without re-processing.

---

### User Story 2 - Know where transcription stands (Priority: P2)

At any moment the user can see, per session, whether live transcription is
keeping up, has fallen behind (and by how much), has finished, or has
failed with a stated reason — and a transcription failure never affects
the recording itself.

**Why this priority**: Live output that silently stalls is worse than none;
trust requires the system to say whether the transcript is current.

**Independent Test**: During a live session, observe state `live` with a
lag figure that stays bounded; after stop, observe `finalising` →
`completed`; force a failure and verify a clear `failed` state with reason
while recording continues untouched.

**Acceptance Scenarios**:

1. **Given** live transcription is running, **When** the user checks its
   status, **Then** they see `live` plus the current lag (how far behind
   real time the transcript is).
2. **Given** transcription has failed mid-session, **When** the user checks
   status, **Then** they see `failed` with a human-readable reason, and
   the recording session continues capturing normally.
3. **Given** a session whose live transcription failed or fell behind,
   **When** the session ends, **Then** the user can request a full
   transcription of the stored audio (US3 path) to obtain a complete
   transcript.

---

### User Story 3 - Transcribe stored sessions on demand (Priority: P3)

Sessions recorded before this feature existed, sessions whose live
transcription failed or was incomplete, and crash-`interrupted` sessions
can each be transcribed from their stored audio at any later time.

**Why this priority**: The recorder has been accumulating sessions since
feature 001 shipped, and live transcription can legitimately fall short;
stored audio's value must never be stranded.

**Independent Test**: Pick a pre-existing session from feature 001's era,
request transcription, and verify a normal, complete transcript results.

**Acceptance Scenarios**:

1. **Given** any stored non-active session with audio on disk, **When**
   the user requests transcription, **Then** a complete transcript is
   produced with visible progress and becomes the session's current
   transcript; any earlier (e.g. live) transcript is kept, marked
   superseded, and still readable on request.
2. **Given** an on-demand transcription that failed, **When** the user
   requests it again, **Then** the system retries from scratch rather
   than refusing forever, and the session's audio is untouched.

---

### User Story 4 - Transcription never disturbs recording (Priority: P4)

Live transcription runs alongside capture, and on-demand jobs may overlap
a new meeting — neither may degrade recording: no lost audio, no blocked
session start, no noticeable impact on the live call.

**Why this priority**: Constitution Principle VII (sessions are sacred);
the recorder's core duty outranks the transcript. If something must give
under load, it is transcription latency, never captured audio.

**Independent Test**: Run a live-transcribed session under load and verify
zero chunk loss; start an on-demand job on a long stored session, then
start a new recording mid-job; verify recording starts within its 2-second
budget and captures cleanly.

**Acceptance Scenarios**:

1. **Given** live transcription is running for the active session,
   **When** the machine is under load (e.g. a video call), **Then**
   transcription lag may grow but zero audio chunks are lost.
2. **Given** an on-demand transcription in progress, **When** a recording
   session starts, **Then** the recording starts within feature 001's
   guarantees and the on-demand job yields (pauses or throttles) so live
   transcription of the new session takes priority.

---

### Edge Cases

- A session with one silent track (e.g. loopback silence gaps, or a source
  that ended via device loss): the present track is transcribed; missing
  spans simply produce no segments — never an error.
- Speaker bleed (field-verified): system playback is audible on the mic
  track at ~¼–½ volume. Speech captured on both tracks MUST be attributed
  to the track where it is primary (louder/clearer), not transcribed twice.
- Overlapping speech (both sides talking at once): both segments appear,
  each attributed to its own track, overlapping in time.
- Non-speech audio (music, notification chimes): may yield empty or garbage
  segments; the transcript MUST NOT fail outright, and silence/noise spans
  produce no text.
- Live transcription falls behind real time (machine under load): audio
  is never skipped — every utterance is still transcribed, just later;
  lag is reported honestly and shrinks when load eases. If the session
  stops with a backlog, the state stays `finalising` until the backlog
  drains, so `completed` always means the transcript is whole (SC-007's
  30 s is the normal-load target, not a cap under sustained overload).
- Live transcription fails mid-session (e.g. speech engine crash):
  recording continues unaffected; status shows `failed`; the completed
  session remains fully transcribable on demand.
- Very long sessions (~4 h): live transcription keeps its lag bounded and
  memory flat; on-demand transcription completes without exhausting
  memory or storage budgets.
- Recorder restart mid-session (crash): live transcript segments produced
  before the crash are preserved with the interrupted session; the
  remainder is available via on-demand transcription — nothing is
  silently abandoned in a `live` state.
- Recorder restart mid on-demand job: the job is restarted or resumed
  automatically; it is never silently abandoned in `running`.
- Live stream consumer disconnects and reconnects (UI reload, network
  blip on localhost): resubscribing from its last-seen cursor yields
  exactly the missed segments — no gap, no duplicate.
- Non-English speech: v1 targets the user's primary language (English);
  other languages transcribe on a best-effort basis without failing.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST convert both capture tracks (microphone and
  system audio) of a session into text on the local machine — live while
  the session is being recorded, and from stored audio for non-active
  sessions.
- **FR-002**: The system MUST produce, per session, a single chronological
  transcript of segments, each carrying: start time, end time, spoken
  text, and source attribution (`me` = microphone, `them` = system audio).
  During a live session the transcript grows incrementally; segments
  already delivered are stable (a delivered segment's text does not later
  change) so that consumers can render as they arrive.
- **FR-003**: Speech audible on both tracks due to acoustic bleed MUST
  appear exactly once in the transcript, attributed to the track where it
  is primary.
- **FR-004**: Transcripts MUST be stored durably, associated with their
  session, and retrievable repeatedly without re-processing; they MUST
  survive recorder restarts.
- **FR-005**: The system MUST expose transcription state per session
  (`none | live | finalising | queued | running | completed | failed`),
  including current lag while `live`, progress while `running`, and a
  human-readable reason on failure, via the local API with typed schemas.
- **FR-006**: A failed transcription (live or on-demand) MUST be
  retryable via an on-demand pass and MUST NOT modify or damage the
  session's audio or metadata.
- **FR-007**: Any stored non-active session with surviving audio —
  including `interrupted` sessions and sessions recorded before this
  feature — MUST be transcribable on demand. An on-demand result becomes
  the session's *current* transcript; any prior transcript (e.g. the live
  one) is retained, marked superseded, readable on explicit request, and
  never destroyed.
- **FR-008**: Transcription MUST NOT violate feature 001's recording
  guarantees: session start ≤ 2 s and zero chunk loss while any
  transcription work exists (live, pending, running, or finalising).
  Under contention, transcription latency yields; capture never does.
- **FR-009**: All processing and all transcript data MUST remain on the
  local machine (constitution Principle I). No audio, text, or derived
  data leaves the device.
- **FR-010**: Live transcription MUST start automatically when a
  recording session starts and MUST finalise automatically when the
  session stops, without user action. On-demand transcription of a
  non-active session is explicitly requested by the user.
- **FR-011**: The system MUST deliver live segments to consumers as they
  are produced (push-style, not only on poll), so a UI can render the
  transcript in near real time. Subscription is cursor-based: a consumer
  supplies the last segment it has seen (or none) and receives exactly
  the segments after it, so a consumer that connects late or reconnects
  after a drop can combine "transcript so far" + stream with no gaps and
  no duplicates.
- **FR-012**: When a live-transcribed session ends, the transcript MUST be
  finalised (all captured audio up to the stop accounted for) before the
  state becomes `completed`; consumers can distinguish "still finalising"
  from "done".
- **FR-013**: Live transcription MUST NOT skip or drop audio to reduce
  lag. Under overload the transcript becomes late, never incomplete; the
  live result for a session is therefore content-equivalent to what an
  on-demand pass over the same audio would produce.

### Non-Functional Requirements

- **NFR-001**: Live transcription MUST keep up with real time on the
  target hardware: steady-state lag (utterance spoken → segment
  delivered) ≤ 15 s at p95, and lag MUST NOT grow without bound over a
  2-hour session (throughput ≥ 1× real time for two tracks). (Relaxed
  from 10 s on 2026-08-18: v1 rides the 10 s durable-chunk cadence so
  live transcription stays decoupled from capture — constitution VII;
  an utterance straddling a chunk boundary lands one chunk later.
  Sub-second streaming is the named upgrade path.)
- **NFR-002**: On-demand transcription of a 60-minute session MUST
  complete in 30 minutes or less (≥ 2× real time, both tracks, measured
  end-to-end). (Amended 2026-08-19 from ≥ 4×: the original figure was
  written against a single-track mental model; measured on the target
  GPU, `medium` decodes dense two-track meeting speech at a hardware
  ceiling of ~2.0× — the worker achieves 1.93× on a 69-minute real
  recording, i.e. no pipeline overhead to remove. Users who want faster
  backfill can select `small` for on-demand (≈ 7× two-track) at an
  accuracy cost — see research R2.)
- **NFR-003**: Transcription MUST fit the constitution's VRAM budget:
  everything it loads fits within 8 GB *together with a reserved
  allocation for a quantised 3–4B LLM* (the constitution's default
  co-resident, ~3–4 GB, for the future assistant feature), with ≥ 1 GB
  headroom — arithmetic stated in the plan. Live transcription also runs
  co-resident with active capture, so its steady-state CPU/RAM footprint
  is additive to feature 001's and MUST leave a live video call
  unaffected.
- **NFR-004**: Stored transcript data for a session MUST be at most 5% of
  that session's audio size (text plus timing metadata is small).

### Key Entities

- **TranscriptionJob**: The transcription activity for one session —
  mode (`live | on_demand`), state (`live | finalising | queued | running
  | completed | failed`), lag (live) or progress (on-demand), timestamps,
  failure reason; at most one active job per session.
- **Transcript**: One durable transcription result for a session — an
  ordered collection of segments plus provenance (mode that produced it,
  when, from which session), a `final` flag, and a `superseded` flag. A
  session may accumulate several transcripts over time (e.g. live, then
  on-demand); exactly one is *current* (the newest non-failed), and only
  the current one is returned by default.
- **TranscriptSegment**: One attributed utterance — a monotonically
  increasing sequence number within its transcript (the stream cursor),
  start/end time (relative to session start), source (`me | them`), text;
  stable once delivered.

## Out of Scope *(this feature)*

- Summarisation, action items, or any LLM-based post-processing.
- Search across transcripts (future library/search feature).
- Speaker diarisation beyond the two-track `me`/`them` split (no
  distinguishing multiple remote speakers).
- A visual live-caption UI (this feature delivers the live segment stream
  via the local API; rendering it belongs to the web UI feature).
- Revising already-delivered segments with later context (v1 segments are
  stable once delivered; refinement passes are future work).
- Editing or correcting transcripts.
- Translation; multi-language optimisation beyond best-effort.
- Acoustic echo cancellation (the bleed rule in FR-003 is an attribution
  rule, not signal processing).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a scripted two-sided test recording, every scripted
  utterance appears in the transcript exactly once, in correct order, and
  ≥ 90% of utterances carry the correct `me`/`them` attribution —
  including passages where bleed makes speech audible on both tracks.
- **SC-002**: During a live session on the target hardware, ≥ 95% of
  utterances appear in the transcript within 15 seconds of the utterance
  ending, and lag does not trend upward over a 2-hour session.
- **SC-003**: A 60-minute stored session yields its complete on-demand
  transcript within 30 minutes of the job starting (see NFR-002
  amendment, 2026-08-19).
- **SC-004**: A live-transcribed 2-hour session records with zero lost
  chunks; starting a recording session while an on-demand job runs
  succeeds within 2 seconds (feature 001's guarantees hold unchanged).
- **SC-005**: Transcription state is always inspectable: at any moment the
  API reports a state from the defined set (with lag while live, reason
  when failed); live segments reach a subscribed consumer without
  polling; contract tests pass for all payloads.
- **SC-006**: A session from before this feature transcribes successfully
  on demand with no manual data migration.
- **SC-007**: When a session stops, its transcript reaches `completed`
  (final, all captured audio accounted for) within 30 seconds of the stop
  under normal load (under sustained overload the backlog drains first —
  FR-013 — visibly in `finalising`).

## Assumptions

- Two-track attribution (`me`/`them`) is sufficient for v1; the system
  audio track may contain multiple remote voices all labelled `them`.
- Live transcription starts automatically with every recording session
  (decision 2026-08-18); there is no per-session opt-out in v1 — a
  session is always transcribed live *when transcription is installed*.
  On a capture-only install (transcription components absent) live mode
  is skipped entirely and sessions have transcription state `none`,
  exactly like feature-001-era sessions — not a `failed` transcript per
  session. Installed-but-not-ready (model missing, engine error) IS a
  visible `failed`, because the user set it up and expects it to work.
  If auto-start becomes undesirable, an opt-out is a small follow-up.
- Live segments are delivered at utterance granularity (a few seconds of
  speech), not word-by-word; the lag bound is measured from utterance
  end to segment delivery.
- English is the primary target language.
- Transcripts and the live stream are consumed via the local API (same
  pattern as feature 001); a human-readable export/UI is future work.
- The existing chunked 16 kHz mono per-track format from feature 001 is
  the input for both modes; no re-recording or format migration is
  needed. Live mode consumes audio as it is captured; on-demand mode reads
  the stored chunks.
- At most one live job (the active session) and one on-demand job run at
  a time; when both exist, live has priority (FR-008).
