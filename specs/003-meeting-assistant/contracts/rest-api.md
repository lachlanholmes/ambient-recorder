# Contract: Assistant API (REST + WebSocket)

Extends the existing API: same base URL, loopback bind, error envelope.
Normative schemas: `src/ambient_recorder/models/assistant.py`.

## New error codes (added to `ErrorCode`, own contract commit)

`assistant_not_ready | transcript_not_final | summary_not_found |
conversation_not_found | turn_not_found`

## GET /assistant/readiness

- **200** → `AssistantReadiness`. Never errors; `ready:false` carries a
  remedy `reason`.

## POST /sessions/{id}/summarize

- **202** → `AssistantTaskResponse` (task queued; new summary id).
- **404** `session_not_found`; **409** `transcript_not_final` (session
  active, or transcript live/finalising/absent); **503**
  `assistant_not_ready`.
- Re-summarising is always allowed (new version supersedes-but-keeps).

## GET /sessions/{id}/summary — current

- **200** → `SummaryResponse` (full structure + provenance + task state
  while pending). **404** `summary_not_found` if none ever requested.

## GET /sessions/{id}/summaries / GET /sessions/{id}/summaries/{sid}

- **200** → version list (newest first, `superseded` flags) / one
  specific version. **404** accordingly.

## POST /conversations

Conversations are **top-level** (analyze decision 2026-08-24): a chat
about a declared scope of sessions, not a child of one.

- Body: `{"session_ids": ["…"]}` — **v1: exactly one** entry.
- **201** → `ConversationResponse` (id, session_ids, `born_live` true if
  any scoped session is active). **404** `session_not_found` (unknown
  id in scope); **422** `validation_error` (empty or >1 in v1); **503**
  `assistant_not_ready`.

## GET /conversations?session_id={id} / GET /conversations/{cid}

- **200** → list, newest first (`session_id` filter optional) / one
  conversation with all turns. **404** `conversation_not_found`.

## POST /conversations/{cid}/ask

- Body: `{"question": "…"}` (non-empty, ≤ 2000 chars).
- **202** → `TurnResponse` (turn id, seq, state `streaming`; queued —
  live asks jump the queue, R5).
- **404** `conversation_not_found`; **503** `assistant_not_ready`.
- Asks work whenever a scoped session has any transcript (final,
  interrupted, or live-so-far per FR-003/FR-010); only *summaries*
  require finality. Grounding for live scoped sessions uses the
  transcript-so-far.

## WS /conversations/{cid}/stream

Flat path by design — conversations are top-level resources, so `cid`
alone identifies the stream. One in-flight turn per conversation;
frames:

```json
{"type": "token", "turn_seq": 4, "text": "The new date "}
{"type": "status", "turn_seq": 4, "state": "streaming"}
{"type": "status", "turn_seq": 4, "state": "completed",
 "citations": [{"session_id": "…", "transcript_id": "…", "seq": 41, "start_s": 724.1}],
 "watermark": "live:213"}
```

- On connect: replay the in-flight turn's accumulated prefix as one
  `token` frame, then tail live tokens; if no turn is in flight, send
  the latest turn's terminal status and close.
- Terminal states: `completed | ungrounded | declined | failed |
  interrupted` (the last only ever seen on the connect-replay path — a
  restart killed the answer mid-stream and the prefix was preserved) —
  after sending one, the server closes. Close 4404 unknown conversation.
- A disconnected client reads the stored turn via GET (FR-012).

## Contract tests (REQUIRED)

1. Round-trip every model (SC-006).
2. Every endpoint status above via `FakeAssistantEngine`, including
   scope validation (empty / two sessions → 422 in v1).
3. WS: prefix-replay + tail exactness, terminal-status close, 4404.
4. Priority: a live ask enqueued behind a running summary is served
   first (fake engine with controllable delays).
5. OpenAPI surface guard updated (REST); WS route asserted via app
   routes.
