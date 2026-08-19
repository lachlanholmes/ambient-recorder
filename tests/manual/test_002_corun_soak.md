# 002 manual: 2-hour live-transcribed co-run soak (T036, SC-004/SC-002/NFR-003)

Setup: recorder running, transcription ready; a real or simulated
meeting (video call, or a long talk playing) so both tracks have signal.

1. Start a session titled `soak-002`; leave it 2 h.
2. Sample at ~30/60/90 min (Task Manager → python.exe; `nvidia-smi`):
   - CPU %: ______ / ______ / ______  (feature 001 baseline was 0.1%)
   - RAM MB: ______ / ______ / ______ (001 baseline ~41 MB)
   - GPU mem MB: ______ / ______ / ______ (expect ≈ 1100 steady)
   - GPU util %: ______ (bursty; idle between chunks)
   - Video call subjectively unaffected? ______
3. `ws_tail.py` the session for a few minutes at each sample; note the
   lag column: p95 ______ s (PASS ≤ 15 s), no upward trend.
4. Stop. From inspect: `chunk_counts` mic ______ / system ______
   (≈ 720 each — system now gap-filled so should match), zero `.part`
   orphans, transcript `completed final=true` within ______ s.
5. Contention: start an on-demand job on another long session, then
   `time curl -X POST /sessions …` → ______ s (PASS ≤ 2 s); confirm the
   on-demand job's progress pauses while live chunks arrive.

Result (date, pass/fail): ______________________________________
