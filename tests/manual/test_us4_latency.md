# US4 manual: warm-start latency (T032, SC-004 strict 2 s)

1. Leave the recorder running ≥ 10 minutes (idle).
2. Three times, run:
   `time curl -s -X POST 127.0.0.1:8377/sessions -H 'content-type: application/json' -d '{}'`
   then stop the session.
3. PASS if each request completes in ≤ 2 s AND the recorder's
   `start_latency` log event reports `latency_s` ≤ 2.0 (request → first
   captured frame — the truer metric; keep audio playing so the loopback
   source has frames to deliver).
4. No recorder restart may occur at any point during the three runs.
