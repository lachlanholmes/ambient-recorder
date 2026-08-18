# Data Model: Local Transcription

New entities live in `src/ambient_recorder/models/transcript.py`; SQLite
tables in the existing feature 001 database (`storage/transcripts.py`).

## Transcript

One transcription *attempt* for a session. Insert-only versioning:
several may exist per session; the **current** one is the newest whose
state is not `failed`.

| Field | Type | Rules |
|-------|------|-------|
| id | str (ULID) | |
| session_id | str | FK → sessions |
| mode | enum `live \| on_demand` | |
| state | enum `live \| finalising \| completed \| interrupted_live \| failed` | See state machine |
| final | bool | True iff all captured audio is accounted for (`completed` only) |
| superseded | bool | Derived on read: true iff a newer non-failed transcript exists for the session |
| engine | str | e.g. `faster-whisper` |
| model | str | e.g. `medium/int8_float16/cuda` — the degradation choice actually used |
| created_at / finalised_at | datetime (UTC) | |
| failure_reason | str \| None | Human-readable, `failed` only |

**State machine**:

```text
live ──session stop──► finalising ──backlog drained──► completed (final=true)
 │                          │
 │                          └──engine error──► failed
 ├──engine error──► failed
 └──recorder restart while session gone──► interrupted_live (segments kept)

on_demand:  (job running) ──done──► completed (final=true)
                          └──error─► failed
```

- A `live` transcript is created atomically when its session starts
  (FR-010) — if the engine is not ready, the transcript is created
  directly as `failed` with reason `engine_not_ready` so state is always
  inspectable (SC-005).
- Exactly one non-terminal transcript per session at a time.

## TranscriptSegment

| Field | Type | Rules |
|-------|------|-------|
| transcript_id | str | FK → transcripts |
| seq | int | 0-based, contiguous per transcript, assigned by the store on insert; **the stream cursor** |
| source | enum `me \| them` | `me` = mic track, `them` = system track (FR-003) |
| start_s / end_s | float | Session-relative seconds; `end_s > start_s` |
| text | str | Non-empty, stripped |

- Immutable once inserted (FR-002 stable segments); ordering by
  `(start_s, seq)` for display; `seq` alone for cursors.
- Segments removed by the bleed rule (research R4) are never inserted —
  the transcript contains only kept segments.

## TranscriptionJob

The scheduling record; one per transcript.

| Field | Type | Rules |
|-------|------|-------|
| transcript_id | str | FK, unique |
| session_id | str | |
| mode | enum `live \| on_demand` | |
| state | enum `queued \| running \| finalising \| completed \| failed` | mirrors Transcript.state for on-demand; `live` maps to `running` |
| priority | int | 0 live, 1 on-demand (research R6) |
| progress_chunks / total_chunks | int | on-demand progress; live: total unknown (null) |
| lag_s | float \| None | live only: now − end_s of newest delivered segment, updated per chunk |
| enqueued_at / started_at / ended_at | datetime | |
| failure_reason | str \| None | |

## TranscriptionReadiness (API-only)

| Field | Type |
|-------|------|
| ready | bool |
| engine | str \| None |
| model | str \| None (chosen per degradation) |
| device | enum `cuda \| cpu` \| None |
| free_vram_mb / required_vram_mb | int \| None |
| reason | str \| None — e.g. `model_missing: run <cmd>` |

## SQLite notes

- Tables: `transcripts`, `transcript_segments`, `transcription_jobs`;
  index `transcript_segments(transcript_id, seq)` unique; index
  `transcripts(session_id, created_at DESC)`.
- Same single-writer discipline as feature 001's metadata store; the
  transcription worker is the only writer of these tables.
- Startup reconciliation (research R7) runs after feature 001's, before
  serving requests.
