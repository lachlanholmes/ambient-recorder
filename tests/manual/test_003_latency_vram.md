# 003 manual: latency + VRAM co-residency (T031)

Prereq: readiness `ready`; a ~60-min session with final transcript
(the 001 soak or a slice) and a live session for step 3.

1. **Post-meeting Q&A latency (NFR-002)**: 3 questions on a long
   session via answer_tail.py; first token ≤ 10 s (incl. cold model
   load on the first), complete ≤ 60 s.
   - firsts: ___ / ___ / ___ s; completes: ___ / ___ / ___ s
2. **60-min summary (NFR-001/SC-002)**: `time` the summarize of a
   ~60-min session → ___ min (PASS ≤ 3 min). Then the 5-hour soak
   (01M0G93XVGEMHY6NJA6X4Q3MAK — backfill its transcript first if only
   interrupted_live) → completes without error: ___
3. **Live co-residency (NFR-003/NFR-004, SC-004/SC-005)**: start a
   session with audio playing; ask about minute-old content:
   - live first token: ___ s (PASS ≤ 15) — watermark `live:<seq>`: ___
   - `nvidia-smi` while answering (STT + LLM resident): ___ MiB
     (PASS ≤ 7000 with ≥ 1 GB headroom on 8188)
   - STT lag stays in bound during the answer (lag_report logs): ___
   - zero chunk loss at stop (chunk_counts vs duration): ___
4. **Egress (SC-007)**: Resource Monitor during 1–3: recorder + ollama
   processes show loopback connections only: ___

Result (date, model, pass/fail): ______________________________________
