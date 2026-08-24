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

## POST /sessions/{id}/conversations

- **201** → `ConversationResponse` (id; `born_live` reflects session
  state). **404** session; **503** `assistant_not_ready`.

## GET /sessions/{id}/conversations / GET …/conversations/{cid}

- **200** → list (newest first) / one conversation with all turns.
- **404** `conversation_not_found`.

## POST /sessions/{id}/conversations/{cid}/ask

- Body: `{"question": "…"}` (non-empty, ≤ 2000 chars).
- **202** → `TurnResponse` (turn id, seq, state `streaming`; queued
  behind at most the in-flight task — live asks jump the queue, R5).
- **404** conversation/session; **409** `transcription_already_running`
  is NOT reused — asks are always queueable; **503**
  `assistant_not_ready`.
- Live asks (session active) are permitted and grounded on the
  transcript-so-far; post-meeting asks require the current transcript
  final? **No** — asks work whenever a transcript exists (final or
  live); only *summaries* require finality.

## WS /conversations/{cid}/stream

One in-flight turn per conversation; frames:

```json
{"type": "token", "turn_seq": 4, "text": "The new date "}
{"type": "status", "turn_seq": 4, "state": "streaming"}
{"type": "status", "turn_seq": 4, "state": "completed",
 "citations": [{"transcript_id": "…", "seq": 41, "start_s": 724.1}],
 "watermark": "live:213"}
```

- On connect: replay the in-flight turn's accumulated prefix as one
  `token` frame, then tail live tokens; if no turn is in flight, send
  the latest turn's terminal status and close.
- Terminal states: `completed | ungrounded | declined | failed` — after
  sending one, the server closes. Close 4404 unknown conversation.
- A disconnected client reads the stored turn via GET (FR-012).

## Contract tests (REQUIRED)

1. Round-trip every model (SC-006).
2. Every endpoint status above via `FakeAssistantEngine`.
3. WS: prefix-replay + tail exactness, terminal-status close, 4404.
4. Priority: a live ask enqueued behind a running summary is served
   first (fake engine with controllable delays).
5. OpenAPI surface guard updated (REST); WS route asserted via app
   routes.
