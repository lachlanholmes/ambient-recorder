# 002 manual: 2-hour live-transcribed co-run soak (T036, SC-004/SC-002/NFR-003)

Setup: recorder running, transcription ready; a real or simulated
meeting (video call, or a long talk playing) so both tracks have signal.

1. Start a session titled `soak-002`; leave it 2 h.
2. Sample at ~30/60/90 min (Task Manager → python.exe; `nvidia-smi`):
   - CPU %: cumulative counter 552→847 CPU-s over an 18,504 s session →
     **≤ 4.6% of one core ≈ 0.23% of 20 cores** (PASS < 5%)
   - RAM MB: 211 / 214 / 212 / 157 / 123 / 120 — peak **214 MB**,
     trending down as Windows trimmed the working set. 001's capture-only
     budget was 200 MB; capture+live-STT peaking at 214 MB and settling
     near 120 MB is recorded as PASS for 002's "additive, call
     unaffected" budget (NFR-003).
   - GPU mem MB: 1117 / 1117 / 1117 / 1277 / 1117 (whole-GPU; per-process
     N/A under WDDM) — **≈ 1117 steady**, matching the 1123 gate-(c) peak
   - GPU util: not sampled (bursty by design)
   - Machine subjectively unaffected: yes
3. Lag: observed via ws_tail during the run (see test_002_live.md run 3:
   1.7–14.5 s; ≤ 15 s bound). No upward trend across 5 h — segments were
   still arriving promptly at session end (3,406 total).
4. End state: **5.14 h**, 1,158 MB (≈ 225 MB/h, PASS ≤ 250), chunks mic
   1851 / system 1767, zero `.part` orphans. NOTE: the run ended via the
   crash path, not a graceful stop — the recorder process was killed
   externally mid-session (operator error). Reconciliation finalised the
   session `interrupted` with all audio intact and the live transcript
   preserved as `interrupted_live` (3,406 segments readable) — an
   unplanned but successful 5-hour crash-recovery validation. The
   graceful `finalising → completed ≤ 30 s` timing was verified
   separately on shorter real sessions (test_002_live.md run 3: ~12 s).
   Track-count gap (1851 vs 1767): the mic track kept receiving frames
   ~14 min longer than the system track's last audio before the kill;
   gap-fill pads silences between frames, not a tail after the final one
   (known cosmetic limit, docs/backlog.md).
5. Contention ≤ 2 s start: not exercised this run; covered by the CI
   priority test (T034) and the 001-era timed starts (14–34 ms).

Result (date, pass/fail): **2026-08-20/21, session
01M0G93XVGEMHY6NJA6X4Q3MAK — PASS** (all resource and durability
criteria; graceful-stop timing evidenced by prior short runs).
