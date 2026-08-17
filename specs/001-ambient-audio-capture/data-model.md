# Data Model: Ambient Audio Capture Sessions

Entities from the spec, with fields, validation, and state machines. All
entities are Pydantic models in `src/ambient_recorder/models/session.py`;
SQLite tables mirror them 1:1 (no ORM, explicit column lists).

## Session

A bounded recording with a status lifecycle. Owns its capture sources and
events.

| Field | Type | Rules |
|-------|------|-------|
| id | str (ULID) | Unique, generated at creation; also the session directory name |
| title | str \| None | Optional, ≤ 200 chars, stripped |
| status | enum `active \| completed \| interrupted` | See state machine |
| started_at | datetime (UTC) | Set when first frames arrive from both sources |
| ended_at | datetime (UTC) \| None | Set on stop or reconciliation |
| duration_s | float \| None | Derived from persisted audio length, NOT wall clock (spec edge case) |
| size_bytes | int | Sum of finalised chunk sizes across sources |
| dir_path | str | `data/sessions/<id>/`, relative to data root |
| created_at | datetime (UTC) | Row creation time |

**State machine** (only these transitions are legal):

```text
(create+start, atomic) ──► active ──stop──────────────────► completed
                              │──all sources device-lost──► completed
                              └──startup reconciliation───► interrupted
```

- Create and start are one atomic operation (POST /sessions): preflight
  (devices FR-005/FR-012, disk FR-007) must pass, streams open, then the
  row is written with `active`. No dormant "created" state exists — a
  failed preflight creates nothing (US3 acceptance 1).
- Exactly one session may have status `active` at any time (spec
  Assumptions); enforced by a partial unique index.
- `interrupted` is set ONLY by startup reconciliation (FR-008), never by a
  request.

## CaptureSource

One input of a session. A session has exactly two in v1: `mic` and
`system`.

| Field | Type | Rules |
|-------|------|-------|
| session_id | str | FK → Session |
| kind | enum `mic \| system` | Unique per session |
| device_id | str | OS device identity captured at start (FR-004) |
| device_label | str | Human-readable device name |
| native_rate_hz | int | Device rate at open (typically 48000) |
| persisted_format | const | `16000 Hz, mono, s16le` (NFR-002; stored for forward-compat) |
| status | enum `active \| completed \| ended_device_lost` | See below |
| ended_at | datetime (UTC) \| None | Set when the source stops producing |
| chunk_count | int | Finalised chunks only |

**Source status rules**:

- `ended_device_lost` implements FR-011: the source ends at point of loss,
  the session keeps going on the surviving source. A `device_lost` event is
  appended. No auto-reconnect in v1.
- Session stop marks still-`active` sources `completed`.
- If BOTH sources end via device loss, the session is finalised
  `completed` with both sources `ended_device_lost` (nothing left to
  capture; the recording up to that point is preserved). Decision
  confirmed 2026-08-17: `completed`, not `interrupted` — all capturable
  audio was captured; `interrupted` is reserved for process death
  (reconciliation). The `device_lost` events distinguish this ending.

## AudioChunk

An incrementally persisted segment; ordered, contiguous, individually
valid (a finalised WAV file).

| Field | Type | Rules |
|-------|------|-------|
| session_id | str | FK → Session |
| source_kind | enum `mic \| system` | FK → CaptureSource |
| seq | int | 0-based, contiguous per (session, source); gaps are a reconciliation error |
| file_path | str | `data/sessions/<id>/<kind>/chunk_<seq:06d>.wav` |
| duration_s | float | 10.0 for all but the final chunk; final chunk ≤ 10.0 |
| size_bytes | int | > 44 (header) |
| written_at | datetime (UTC) | Finalise (rename) time |

- A chunk row is inserted only AFTER the atomic rename (research R3);
  `.part` files never appear in metadata.
- Max data-loss window = one in-flight chunk per source (FR-002).

## SessionEvent

Append-only audit trail per session (FR-004's status story + FR-011's
device-loss record).

| Field | Type | Rules |
|-------|------|-------|
| session_id | str | FK → Session |
| at | datetime (UTC) | |
| type | enum `started \| stopped \| device_lost \| default_output_changed \| disk_low \| reconciled` | |
| detail | JSON object | Typed per event type in models (e.g. `device_lost` carries `kind`, `device_id`, `last_seq`) |

## DeviceReadiness (API-only, not persisted)

Result of enumeration (FR-005), returned by `GET /devices`.

| Field | Type | Rules |
|-------|------|-------|
| kind | enum `mic \| system` | |
| status | enum `present \| missing \| default_changed` | `default_changed`: current default differs from the device a previous session used |
| device_id | str \| None | Present when status ≠ missing |
| device_label | str \| None | |

## SQLite schema notes

- Tables: `sessions`, `capture_sources`, `audio_chunks`, `session_events`.
- Partial unique index: `CREATE UNIQUE INDEX one_active ON sessions(status) WHERE status = 'active'`.
- WAL mode; a single writer thread owns all writes (research R4/R6).
- Foreign keys ON; cascade delete is disabled — sessions are never deleted
  in v1 (retention is out of scope).
