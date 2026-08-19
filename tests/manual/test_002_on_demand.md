# 002 manual: on-demand transcription throughput (T033, NFR-002)

```bash
# Pick a long stored session (the 001 soak, 69 min, is ideal):
curl -s 127.0.0.1:8377/sessions | python -m json.tool | head
curl -s -X POST 127.0.0.1:8377/sessions/<id>/transcribe          # 202, note transcript_id
# Poll progress; record wall time from 202 → state completed:
watch -n 5 'curl -s 127.0.0.1:8377/sessions/<id>/transcript | grep -oE "\"state\": \"[a-z_]*\"|progress_chunks\": [0-9]*"'
```

PASS: a 60-min session completes in ≤ 30 min (≥ 2× real time, two
tracks — NFR-002 as amended 2026-08-19; see research R2 for why the
original 4× was a single-track mis-estimate). Record here:

| Date | Session | Audio (min) | Wall (min) | × RT | Pass |
|------|---------|-------------|------------|------|------|
| 2026-08-19 | 01M08RRRZR7F8QX91AYHSZNT9X (001 soak) | 69.3 | 35.9 | 1.93 | **PASS** (beam 1, `medium`; 1907 segments; job was requeued by startup reconciliation after a restart mid-run and completed from scratch — reconciliation verified live) |
| 2026-08-19 | same, beam 5 + O(n²) read bug | 69.3 | 79.2 | 0.88 | FAIL → fixed (in-memory reference set; beam default → 1) |

Fast backfill option: set the on-demand model to `small` (≈ 7× two-
track) when speed matters more than the last few % of accuracy.

Also confirm: `GET /sessions/<id>/transcripts` lists the prior live
transcript (if any) as `superseded:true` and the on-demand one as
current; both readable by id.
