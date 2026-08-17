# Soak: 60-minute session (T035, SC-001 + SC-006/NFR-001)

Setup: recorder running; a real or simulated meeting (e.g. a video call,
or a long video playing) so both sources have signal for the full hour.

1. Start a session titled `soak`; record for 60 minutes.
2. During the run, sample Task Manager (Details → python.exe) at ~15, 30,
   45 min. Record here:
   - CPU %: ______ / ______ / ______  (PASS < 5%)
   - RAM MB: ______ / ______ / ______ (PASS < 200 MB)
   - GPU %: ______ (PASS: 0 — engine never touches the GPU)
3. Stop the session. From the inspect response record:
   - `duration_s`: ______ (≈ 3600)
   - `size_bytes`: ______ (PASS ≤ 250 MB total, SC-001)
   - `chunk_counts`: mic ______ / system ______ (≈ 360 each)
4. Spot-check audio: play the first, a middle, and the last chunk of each
   source with ffplay; both sources intact and separable.
5. Watchdog overhead check: the ~2 s default-device poll spawns a
   short-lived PortAudio instance; confirm the CPU numbers above still
   pass. If they don't, raise `_POLL_INTERVAL_S` in audio/wasapi.py and
   re-run (plan NFR-001 takes precedence over poll frequency).

Result (date, machine, pass/fail): ______________________________________
