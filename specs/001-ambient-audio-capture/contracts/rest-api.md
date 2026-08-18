# Contract: Local REST API

Base URL: `http://127.0.0.1:8377` (port configurable). Localhost-only bind
(FR-010). No authentication in v1 (spec Assumptions). All bodies are JSON;
all schemas are Pydantic models in `src/ambient_recorder/models/api.py` —
that file is the normative contract; this document is its human-readable
form. Contract changes land in the models file first, in their own commit
(constitution II).

## Error envelope (all non-2xx responses)

```json
{
  "error": {
    "code": "device_missing",
    "message": "Required capture device is missing: microphone",
    "detail": {"missing": ["mic"]}
  }
}
```

`code` is a closed enum: `device_missing | session_already_active |
session_not_found | session_not_active | disk_space_low |
validation_error | internal_error`. `detail` is typed per code.

## GET /devices — device readiness (FR-005)

- **200** → `DeviceReadinessResponse`

```json
{
  "sources": [
    {"kind": "mic", "status": "present", "device_id": "…", "device_label": "Headset Microphone"},
    {"kind": "system", "status": "present", "device_id": "…", "device_label": "Speakers (Loopback)"}
  ],
  "ready": true
}
```

`ready` is true iff every source has status `present` (v1 treats
`default_changed` as present-but-flagged; it does not block start).

## POST /sessions — create + start, atomic (FR-006, FR-012)

Request `SessionCreateRequest`:

```json
{"title": "Weekly sync"}        // title optional
```

- **201** → `SessionDetail` (status `active`, both sources `active`)
- **409** `session_already_active` — one-active-session rule
- **422** `validation_error` — malformed body
- **424** `device_missing` — either source unavailable; `detail.missing`
  names the missing kind(s) (SC-003). No session row is created.
- **507** `disk_space_low` — free space below threshold (FR-007);
  `detail` carries `free_mb` and `required_mb`.

## POST /sessions/{id}/stop — finalise (FR-006)

- **200** → `SessionDetail` (status `completed`; final partial chunks
  flushed and finalised before the response returns)
- **404** `session_not_found`
- **409** `session_not_active` — already completed/interrupted

## GET /sessions — list (FR-006)

- **200** → `SessionListResponse`: `{"sessions": [SessionSummary…]}`,
  newest first. `SessionSummary`: id, title, status, started_at, ended_at,
  duration_s, size_bytes.

## GET /sessions/{id} — inspect (FR-006)

- **200** → `SessionDetail`: SessionSummary fields + `sources:
  [CaptureSourceInfo…]` + `events: [SessionEvent…]` + `chunk_counts:
  {"mic": n, "system": m}`. Shapes follow [data-model.md](../data-model.md).
- **404** `session_not_found`

## GET /health — process liveness

- **200** → `{"status": "ok", "version": "…", "active_session_id": null | "…"}`

## Contract tests (REQUIRED — constitution II)

1. Every request/response model round-trips: `Model.model_validate(
   model.model_dump(mode="json"))` is identity (SC-005).
2. Every documented status code above is produced by the route under the
   corresponding condition, using the fake capture provider.
3. Error envelope: every non-2xx body validates against `ErrorResponse`
   and `code` is in the closed enum.
4. OpenAPI export (`app.openapi()`) contains exactly the routes above —
   guards accidental surface growth.
