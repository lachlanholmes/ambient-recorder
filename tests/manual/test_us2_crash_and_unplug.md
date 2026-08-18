# US2 manual: crash survival + device unplug (T025)

## A. kill -9 mid-session (SC-002, FR-008)

1. Start the recorder; note the pid from the first startup log line.
2. `curl -s -X POST 127.0.0.1:8377/sessions -H 'content-type: application/json' -d '{"title":"crash"}'`
3. Record ≥ 3 minutes with audio playing.
4. `kill -9 <recorder-pid>` (Git Bash) — do NOT use a graceful stop.
5. Restart: `python -m ambient_recorder` → startup log shows `session_reconciled`.
6. `curl -s 127.0.0.1:8377/sessions/<id>` and verify:
   - `status` = `interrupted`, exactly one `reconciled` event
   - no `.part` files under `data/sessions/<id>/`
   - last chunk plays: `ffplay data/sessions/<id>/mic/chunk_<last>.wav`
   - lost audio ≤ 10 s per source (compare duration vs wall time recorded)

## B. headset unplug mid-session (FR-011)

1. Start a session using a USB/BT headset as default mic; play audio.
2. After ~30 s, unplug the headset. Within ~2 s (watchdog poll) the log
   shows `wasapi_device_lost` kind=mic.
3. `curl -s 127.0.0.1:8377/sessions/<id>`:
   - session `status` still `active`; mic source `ended_device_lost`
   - one `device_lost` event with `kind`, `device_id`, `last_seq`
4. Keep playing audio ~30 s, stop the session; system audio covers the
   full span, mic audio ends at the unplug point.

## C. default-output switch mid-session (analyze C1)

1. Start a session; play audio through Speakers A.
2. Switch Windows default output to Speakers/Headset B.
3. Within ~2 s the log shows `wasapi_device_lost` kind=system; the system
   source ends `ended_device_lost` (no re-attach in v1); mic continues.
