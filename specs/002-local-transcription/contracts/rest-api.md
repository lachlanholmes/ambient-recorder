# Contract: Transcription API (REST + WebSocket)

Extends feature 001's API. Same base URL, loopback bind, error envelope,
and closed error-code enum (extended below). Normative schemas:
`src/ambient_recorder/models/transcript.py`.

## New error codes

`transcript_not_found | transcription_not_ready | session_still_active |
transcription_already_running` — added to feature 001's `ErrorCode` enum
in its own contract commit.

## GET /transcription/readiness

- **200** → `TranscriptionReadiness` (see data-model.md). Never errors;
  `ready:false` carries a `reason`.

## GET /sessions/{id}/transcript — current transcript

- **200** → `TranscriptResponse`: transcript metadata (id, mode, state,
  final, model) + `segments: [TranscriptSegment…]` ordered by
  `(start_s, seq)` + `job: {state, lag_s, progress_chunks, total_chunks,
  failure_reason}` + `pending_job: {transcript_id, state, progress_chunks,
  total_chunks} | null` — the in-flight on-demand attempt, if any, so a
  client can show "re-transcribing… 40%" while still displaying the
  current (e.g. live) transcript. "Current" = newest transcript that is
  neither `failed` nor `pending`. Query `?after=<seq>` returns only segments with
  `seq > after` (same semantics as the stream cursor).
- **404** `session_not_found`; **404** `transcript_not_found` when the
  session has no transcript at all (legacy session, never transcribed).

## GET /sessions/{id}/transcripts — all attempts (superseded included)

- **200** → `TranscriptListResponse`: `[{id, mode, state, final,
  superseded, model, created_at, finalised_at, segment_count}]`, newest
  first. Read-only history for the supersede-but-keep decision.

## GET /sessions/{id}/transcripts/{transcript_id}

- **200** → `TranscriptResponse` for a specific (possibly superseded)
  attempt. **404** `transcript_not_found`.

## POST /sessions/{id}/transcribe — request on-demand transcription

- **202** → `TranscriptionJobResponse` (job queued; new transcript id).
- **404** `session_not_found`
- **409** `session_still_active` — live mode owns active sessions.
- **409** `transcription_already_running` — an on-demand job for this
  session is already queued/running.
- **503** `transcription_not_ready` — engine/model unavailable;
  `detail.reason` mirrors readiness.

## WS /sessions/{id}/transcript/stream?after=<seq>

Server → client JSON messages, one object per frame:

```json
{"type": "segment", "segment": {"seq": 41, "source": "them", "start_s": 724.1, "end_s": 728.9, "text": "…"}}
{"type": "status",  "state": "live", "lag_s": 3.2, "final": false}
{"type": "status",  "state": "completed", "lag_s": 0.0, "final": true}
```

- On connect: replay all stored segments with `seq > after` (default
  −1 = all), then tail live segments in order. Guarantee: the
  concatenation of replay + tail is exactly the segments after `after`,
  each once (FR-011).
- A `status` frame is sent on connect, on every state change, and at
  least every 5 s while `live`/`finalising`.
- After a `status` with a terminal state (`completed`, `failed`,
  `interrupted_live`) the server closes the socket normally.
- Closes with code 4404 for unknown session, 4409 if the session has no
  transcript.

## Contract tests (REQUIRED)

1. Round-trip every new model (SC-005).
2. Each endpoint produces every documented status via `FakeSpeechEngine`.
3. WebSocket: replay+tail exactness across `after` values including a
   reconnect mid-stream; terminal status closes the socket.
4. `ErrorCode` enum extension appears in the envelope test.
5. OpenAPI surface guard updated to the new route set (WS excluded from
   OpenAPI; asserted via app routes).
