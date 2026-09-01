# Feature Specification: Meeting Assistant

**Feature Branch**: `003-meeting-assistant`

**Created**: 2026-08-23

**Status**: Draft

**Input**: User description: "Meeting assistant (feature 003, from docs/backlog.md): local language-model layer over the attributed transcripts — summaries, action items, and answers to questions about what was said. Inputs are ready from feature 002: `me`/`them` segments with timestamps, a current transcript per session, and a live segment stream. The 002 VRAM plan reserves ~3.5 GB for this feature's model. Everything runs on-device (constitution Principle I); any future frontier-API escalation is a separate opt-in feature operating on redacted text only."

## Clarifications

### Session 2026-08-23

- Q: How far does the assistant go in v1 — summaries only, summaries + post-meeting Q&A, or additionally a live in-meeting assistant? → A: **The full scope (option C)**: summaries, post-meeting Q&A, and a live in-meeting assistant that answers questions during an active session grounded in the transcript-so-far. The LLM is co-resident with live transcription during meetings — the co-residency the VRAM reservation was designed for. The API delivers live answers; rendering them conveniently is the future UI feature's job.

### Session 2026-08-24

- Q: Do Q&A answers stream as they generate, or return only when complete? → A: **Stream** — answer text is pushed incrementally as the model generates (same push pattern as 002's segment stream); the stored Conversation turn keeps the final text and citations, so complete-only consumption falls out by reading the turn after completion. Summaries are tasks (no streaming; poll state, read result).
- Q: One conversation per session or many? → A: **Multiple, explicitly created** — a question either starts a new conversation or continues an existing one by id; each conversation has its own follow-up context; conversations are listable per session. Fresh context on demand instead of follow-ups resolving against arbitrarily old exchanges.
- Q (analyze): Are conversations children of sessions, or top-level? → A: **Top-level, scoped to sessions** — a conversation is a chat with the assistant about a *scope* of recordings, declared at creation as a list of sessions. v1 restricts the scope to exactly one session (retrieval, grounding, and accuracy tests stay single-transcript), but the shape means future cross-session Q&A is only a retrieval upgrade, not an API or schema break.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get a meeting summary (Priority: P1)

After a meeting ends, the user obtains a concise written summary of the
session: the key points discussed, decisions made, and action items —
each action item attributed to whoever committed to it (`me` or `them`)
and carrying any deadline that was spoken.

**Why this priority**: This is the payoff the whole pipeline has been
building toward — audio became transcript, now transcript becomes the
thing a person actually wants five minutes after a meeting: what
mattered and what they owe.

**Independent Test**: Record a short scripted meeting with known
decisions and action items, request its summary, and verify every
scripted decision and action item appears, correctly attributed, with no
invented content.

**Acceptance Scenarios**:

1. **Given** a completed session with a final transcript, **When** the
   user requests its summary, **Then** they receive a structured summary
   (overview, key points, decisions, action items with owner and any
   spoken deadline) derived only from the transcript.
2. **Given** a summary has been produced, **When** the user retrieves it
   again later (including after a recorder restart), **Then** the same
   summary is returned without re-processing.
3. **Given** a session whose transcript is still `live` or `finalising`,
   **When** the user requests a summary, **Then** the request is refused
   with a clear "transcript not final yet" state rather than a partial
   summary.
4. **Given** a session with a superseded transcript history, **When** a
   summary is produced, **Then** it derives from the *current*
   transcript.

---

### User Story 2 - Ask questions about a meeting (Priority: P2)

The user asks a free-form question about a meeting — "what did they say
about pricing?", "what did I commit to?", "when is the new date?" — and
receives an answer grounded in that session's transcript (typically
final; live sessions are US3), citing the moments (timestamps) it drew
from.

**Why this priority**: Summaries answer the questions the system
predicts; Q&A answers the ones it can't. Together they make a recording
searchable by meaning rather than by scrubbing audio.

**Independent Test**: Against a scripted session, ask questions whose
answers are (a) present, (b) absent from the transcript; verify present
answers are correct with plausible citations and absent ones are
answered "not discussed" rather than invented.

**Acceptance Scenarios**:

1. **Given** a completed session, **When** the user asks a question whose
   answer was spoken, **Then** the answer reflects the transcript and
   cites at least one supporting timestamp/segment.
2. **Given** a question whose answer is not in the transcript, **When**
   asked, **Then** the assistant says so plainly instead of guessing.
3. **Given** a multi-turn exchange, **When** the user asks a follow-up
   ("who said that?"), **Then** the assistant resolves it in the context
   of the same conversation.

---

### User Story 3 - Ask during the meeting (Priority: P3)

While a session is recording, the user asks the assistant a question —
"what was the date she just mentioned?", "summarise the last ten
minutes" — and receives an answer grounded in the transcript **so far**,
without the recording or the live transcription missing a beat.

**Why this priority**: This is the ambient vision the project is named
for — a listener you can consult mid-meeting. It builds directly on US2's
Q&A machinery plus feature 002's live stream.

**Independent Test**: During a live scripted session, ask about
something said a minute earlier; verify a correct, cited answer arrives
while chunk capture and live transcription lag stay within their bounds.

**Acceptance Scenarios**:

1. **Given** an active session with live transcription running, **When**
   the user asks a question about what has been said, **Then** the
   answer is grounded in the transcript-so-far with citations, and
   arrives within the live-answer latency bound.
2. **Given** something was said within the last transcription-lag window
   (not yet transcribed), **When** the user asks about it, **Then** the
   assistant answers from what is transcribed and notes it may not have
   caught the very latest moments — never a hang, never a guess.
3. **Given** a live question is being answered, **When** capture and
   transcription continue, **Then** zero chunks are lost and lag stays
   within feature 002's bound (assistant yields under contention).
4. **Given** the session then stops, **Then** the live conversation
   remains readable and can continue post-meeting against the final
   transcript.

---

### User Story 4 - Assistant readiness and honest failure (Priority: P4)

The user can always see whether the assistant is available (model
present, resources sufficient) and, when a summary or answer fails, gets
a stated reason — never a hang, and never any effect on recording or
transcription.

**Why this priority**: Same trust contract as features 001/002: visible
state, typed failures, and the core pipeline is never hostage to the
newest layer.

**Independent Test**: Remove the model, verify readiness reports it with
a remedy and requests fail typed; restore it and verify recovery — all
while a recording session runs undisturbed.

**Acceptance Scenarios**:

1. **Given** the assistant's model is not installed or resources are
   insufficient, **When** the user checks readiness, **Then** they see
   the state and the remedy; summary/Q&A requests are refused with the
   same reason.
2. **Given** an assistant request fails mid-generation, **When** the user
   checks its status, **Then** it is `failed` with a reason and can be
   retried.
3. **Given** an active recording session with live transcription,
   **When** assistant work runs concurrently, **Then** capture loses no
   chunks and live transcription still meets its lag bound.

---

### Edge Cases

- Very long sessions (multi-hour transcripts exceeding what the model
  can read at once): the summary is produced by an approach that covers
  the whole transcript (e.g. staged condensation); nothing after the
  model's horizon is silently ignored.
- Sessions with thin content (a 2-minute test recording, mostly
  silence): the summary says as much — no padding or invention.
- `interrupted` sessions and `interrupted_live` transcripts: summarised
  from what survives, flagged as from an interrupted session.
- Transcription noise (mis-heard words, bleed artefacts): the assistant
  works with the transcript as-is; it does not need to be robust to
  audio, only faithful to text.
- A summary request while another assistant task is running: queued, not
  refused; state shows the queue position or `running`. A *live*
  question outranks queued post-meeting work (the person in the meeting
  is waiting).
- A live question races the session's stop: answered against whatever
  transcript exists when generation starts; the conversation then
  continues against the final transcript.
- Re-summarising after an on-demand re-transcription: allowed; the new
  summary supersedes but keeps the old (same versioning philosophy as
  transcripts).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST generate, on request, a structured summary
  of any session whose current transcript is final: overview, key
  points, decisions, and action items (owner `me`/`them`, spoken
  deadline if any).
- **FR-002**: Summaries MUST be grounded: every statement derives from
  the transcript, and action items/decisions carry at least one
  supporting timestamp reference. The assistant MUST NOT present
  invented content as fact.
- **FR-003**: The system MUST answer free-form questions about a
  session's transcript — final, interrupted, or (per FR-010) the
  transcript-so-far of an active session — citing supporting segments,
  and MUST state plainly when the transcript does not contain an
  answer. Only summaries require a final transcript; questions work
  whenever any transcript exists.
- **FR-004**: Q&A MUST support multi-turn conversations. A conversation
  is a top-level resource created with an explicit scope: the list of
  sessions it may draw on (exactly one in v1; the shape admits more
  later). Multiple conversations may exist over the same session; they
  are listable (all, or filtered by session); follow-up context never
  crosses conversation boundaries.
- **FR-005**: Summaries and Q&A exchanges MUST be stored durably,
  associated with their session and the transcript version they derive
  from, retrievable without re-processing, and surviving restarts.
  Re-generation supersedes-but-keeps (same versioning rule as
  transcripts).
- **FR-006**: The system MUST expose assistant state via the local API
  with typed schemas: readiness (model present/absent with remedy), and
  per-task state (`queued | running | completed | failed` with reason).
- **FR-007**: All assistant processing MUST run on the local machine on
  transcript text only. No audio is ever an assistant input, and nothing
  leaves the device (constitution Principle I; frontier-API escalation
  is explicitly out of scope for this feature).
- **FR-008**: Assistant work MUST NOT violate the guarantees of features
  001/002: zero chunk loss, session start ≤ 2 s, and live transcription
  lag within its bound while assistant tasks run. Under contention the
  assistant yields.
- **FR-009**: A capture-only or transcription-only install MUST behave
  exactly as today: assistant endpoints report `not_installed` readiness
  and sessions/transcripts are unaffected.
- **FR-010**: The assistant MUST answer questions during an active
  session, grounded in the transcript-so-far (consuming feature 002's
  segments as they arrive). Live answers acknowledge the transcription
  lag window when relevant (US3 acceptance 2) and never block on
  untranscribed audio. A live conversation persists and can continue
  post-meeting against the final transcript.
- **FR-011**: During active sessions the assistant's model is
  co-resident with live transcription; assistant inference yields to
  capture and transcription under contention (they own priority 0 and 1;
  assistant work is strictly lower). Between meetings the assistant may
  hold or release resources freely.
- **FR-012**: Q&A answers (live and post-meeting) MUST be delivered as
  an incremental stream while generating, followed by a terminal status
  carrying the validated citations; the completed turn is stored and
  readable afterwards, so complete-only consumption requires no separate
  mode. A consumer that disconnects mid-answer can read the finished
  turn from the stored conversation. Summaries are not streamed: they
  are tasks whose state is polled and whose result is read on
  completion.

### Non-Functional Requirements

- **NFR-001**: A summary of a 60-minute meeting MUST complete within 3
  minutes of the request on the target hardware.
- **NFR-002**: A post-meeting Q&A answer MUST begin appearing within 10
  seconds of the question, with the full answer within 60 seconds, for
  sessions up to 2 hours.
- **NFR-003**: A live in-meeting answer MUST begin appearing within 15
  seconds of the question (it may need to wait out in-flight
  transcription work) and complete within 60 seconds, while live
  transcription stays within its own lag bound.
- **NFR-004**: The assistant MUST fit the constitution's VRAM budget
  co-resident: its model plus feature 002's live transcription (~1.1 GB
  measured) loaded simultaneously within 8 GB with ≥ 1 GB headroom —
  the ~3.5 GB reservation made in the 002 plan, with the arithmetic
  re-stated and re-measured in this feature's plan.
- **NFR-005**: Stored assistant output for a session MUST be small
  relative to its transcript (text only; no practical storage concern —
  bounded by 10% of transcript size).

### Key Entities

- **Summary**: The structured result for one session — overview, key
  points, decisions, action items (owner, deadline, citation) — with
  provenance (transcript version, model, when) and the
  supersede-but-keep versioning of its session's summaries.
- **AssistantTask**: One unit of assistant work (summary generation or
  answer generation) — state (`queued | running | completed | failed`),
  timestamps, failure reason.
- **Conversation**: A top-level multi-turn chat with the assistant about
  a declared scope of sessions (exactly one in v1) — identity, creation
  time, scope, and an ordered list of question/answer turns, each answer
  carrying citations (session-qualified segment references) and the
  transcript watermark it answered against (final, or
  live-up-to-segment-N). Follow-up context is per-conversation; a
  conversation begun live continues seamlessly post-meeting.

## Out of Scope *(this feature)*

- Any cloud/frontier-model escalation (separate future feature; would
  operate on redacted text per the constitution's router clause).
- Cross-session search or questions spanning multiple meetings (future
  library feature — but the conversation model is shaped for it:
  scope is a session list, restricted to length 1 in v1, so lifting the
  restriction later is a retrieval upgrade, not a contract break).
- Editing summaries; exporting to email/documents; calendar or task-tool
  integration.
- A visual UI (the web UI feature will render these; this feature
  delivers the API — live in-meeting answers included, consumed via the
  API until the UI lands).
- Proactive, unprompted assistance (the assistant speaks only when
  asked; auto-surfacing suggestions mid-meeting is future work).
- Automatic summary generation without a user request (can be a later
  toggle; v1 is on-request).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a scripted test meeting with a known answer key
  (5 decisions, 5 action items with owners), the summary captures ≥ 90%
  of the keyed items with correct owner attribution, and contains zero
  statements unsupported by the transcript.
- **SC-002**: A 60-minute real meeting summarises in ≤ 3 minutes; the
  summary of the project's own 5-hour soak session completes without
  error (staged condensation covers the full transcript).
- **SC-003**: For a scripted Q&A set (10 questions: 7 answerable, 3
  not), ≥ 90% of answerable questions are answered correctly with a
  valid citation, and all 3 unanswerable ones are declined rather than
  guessed.
- **SC-004**: During a live scripted session, a question about content
  spoken ≥ 1 minute earlier is answered correctly with a citation,
  first output within 15 s; a question about the not-yet-transcribed
  window is answered with the honest lag caveat, not a guess.
- **SC-005**: Assistant tasks running concurrently with an active
  recording session — including live Q&A with the LLM resident — cause
  zero chunk loss and keep live transcription within its lag bound
  (verified against feature 001/002 test suites and a co-run check).
- **SC-006**: Assistant state is always inspectable via typed API
  payloads; contract tests pass; a missing model yields a readiness
  remedy, not an error on use.
- **SC-007**: All summaries and answers derive from on-device processing
  only — no network egress during any assistant operation.

## Assumptions

- The assistant's model is a locally hosted, quantised small language
  model within the ~3.5 GB reservation; the specific model and runtime
  are plan decisions (the constitution names Ollama with Qwen3 /
  Llama 3.2 3B / Phi-4-mini available).
- English is the primary language, matching transcription.
- Assistant work is serial (one task at a time); queueing is acceptable
  for a single-user machine, with live questions ahead of post-meeting
  work in the queue.
- During meetings the assistant model stays loaded (co-resident with
  STT, decision 2026-08-23); between meetings it may be unloaded to free
  VRAM — a plan decision.
- Summaries operate on final transcripts; Q&A operates on final
  transcripts and, live, on the transcript-so-far.
- "Grounded" is enforced by construction (the model only sees transcript
  text) and validated by the scripted accuracy tests; formal
  hallucination detection is out of scope.
- Install remains layered: capture-only, +transcription, +assistant are
  each valid states with honest readiness reporting.
