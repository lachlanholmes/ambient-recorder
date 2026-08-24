# Data Model: Meeting Assistant

New entities in `src/ambient_recorder/models/assistant.py`; tables in the
existing SQLite (`storage/assistant.py`). Versioning follows 002's
insert-only supersede-but-keep pattern.

## Summary

One summary *attempt* for a session. Current = newest non-failed.

| Field | Type | Rules |
|-------|------|-------|
| id | str (ULID) | |
| session_id | str | FK → sessions |
| transcript_id | str | The transcript version it derives from |
| state | enum `pending \| completed \| failed` | `pending` while its task is queued/running |
| overview | str | Completed only |
| key_points | list[SummaryItem] | text + citations |
| decisions | list[SummaryItem] | text + citations |
| action_items | list[ActionItem] | text, owner `me \| them`, deadline_text (verbatim spoken deadline or null), citations |
| model | str | e.g. `ollama/llama3.2:3b` |
| created_at / completed_at | datetime (UTC) | |
| failure_reason | str \| None | |

- Requestable only when the session's current transcript is `final`
  (FR-001, US1 acceptance 3); refused otherwise with
  `transcript_not_final`.
- Every SummaryItem/ActionItem carries ≥ 1 citation (segment seq into
  transcript_id); enforced at completion (FR-002).

## Conversation

| Field | Type | Rules |
|-------|------|-------|
| id | str (ULID) | |
| session_id | str | FK → sessions |
| created_at | datetime (UTC) | |
| born_live | bool | Started during an active session |

- Multiple per session (clarification 2026-08-24); listable, append-only,
  never superseded.

## ConversationTurn

| Field | Type | Rules |
|-------|------|-------|
| conversation_id | str | FK |
| seq | int | 0-based per conversation; store-assigned |
| question | str | non-empty |
| answer | str | grows while streaming; final on completion |
| citations | list[Citation] | validated segment refs `{transcript_id, seq, start_s}` |
| watermark | str | `final` or `live:<segment seq>` — what the answer saw |
| state | enum `streaming \| completed \| ungrounded \| declined \| failed \| interrupted` | `declined` = honest "not discussed"; `ungrounded` = assertions with zero valid citations (FR-002/R3); `interrupted` = recorder restart mid-answer, prefix kept |
| asked_at / completed_at | datetime (UTC) | |

## AssistantTask

| Field | Type | Rules |
|-------|------|-------|
| id | str (ULID) | |
| kind | enum `summary \| ask` | |
| ref_id | str | summary id or turn id |
| session_id | str | |
| priority | int | 0 live ask, 1 ask, 2 summary (R5) |
| state | enum `queued \| running \| completed \| failed` | |
| enqueued_at / started_at / ended_at | datetime | |
| failure_reason | str \| None | |

Startup reconciliation (R7): `running` summary → requeued from scratch;
`running` ask → turn `interrupted` (streamed prefix kept), task `failed`.

## AssistantReadiness (API-only)

| Field | Type |
|-------|------|
| status | enum `ready \| not_ready \| not_installed` — `not_installed`: Ollama unreachable AND never configured (layered install, FR-009); `not_ready`: reachable but model missing / VRAM policy failed |
| ready | bool (derived) |
| runtime | str \| None (`ollama <version>`) |
| model | str \| None |
| reason | str \| None — remedy text, e.g. `model_missing: ollama pull llama3.2:3b` |

## SQLite notes

- Tables `summaries`, `conversations`, `conversation_turns`,
  `assistant_tasks`; unique index `conversation_turns(conversation_id,
  seq)`; index `summaries(session_id, created_at DESC)`.
- Single writer: the assistant worker owns all writes to these tables.
- Citations stored as JSON columns (bounded, read-only after write).
