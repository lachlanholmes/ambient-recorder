# US3 manual: preflight readiness (T029, SC-003)

## A. missing device → 424, nothing created

1. Disable the microphone (Settings → Privacy → Microphone, or unplug).
2. `curl -s 127.0.0.1:8377/devices` → mic `missing`, `ready: false`.
3. `curl -s -X POST 127.0.0.1:8377/sessions -H 'content-type: application/json' -d '{}'`
   → HTTP 424, `error.code` = `device_missing`, `error.detail.missing` = `["mic"]`,
   message names the microphone.
4. `curl -s 127.0.0.1:8377/sessions` → no new session appeared.
5. Re-enable the mic → `/devices` shows `present`, start succeeds (201).

## B. low disk → 507

1. Restart the recorder with an impossible threshold:
   `AMBREC_MIN_FREE_DISK_MB=999999999 python -m ambient_recorder`
2. POST /sessions → HTTP 507, `error.code` = `disk_space_low`,
   `detail.free_mb` / `detail.required_mb` populated; no session created.

## C. default_changed flag

1. Complete any session, then switch the Windows default output device.
2. `curl -s 127.0.0.1:8377/devices` → system source `default_changed`,
   `ready` stays `true` (does not block start in v1).
