# Feature 004 — Web UI validation record

Protocol: `specs/004-web-ui/quickstart.md` (Scenarios 1–7), performance
targets NFR-001/002/003, egress check SC-004. Status legend:
**VERIFIED** (machine-checked this run) · **PENDING** (needs the
browser walkthrough).

## Run 2026-09-01 — implementation session (automated portion)

Environment: recorder from source (editable install), real data root,
transcription ready (`medium/int8_float16/cuda`, 7.9 GB free VRAM),
assistant ready (ollama 0.32.15, phi4-mini).

### Machine-verified

| Check | Result |
|---|---|
| Serving contract (`/` + CSP header + no-cache index, API mount-order guard, missing-ui degradation, OpenAPI surface unchanged) | VERIFIED — `tests/contract/test_ui_serving.py`, 6 tests green |
| Local-only assets (no non-loopback URL in any shipped UI file) | VERIFIED — `tests/contract/test_ui_local_only.py` green |
| Full regression (001–003 suites) | VERIFIED — 221 passed |
| ES-module integrity (every import resolves to a real export; syntax) | VERIFIED — node parse + static cross-check, all clean |
| 5-h fixture API side (SC-003 input): `GET /sessions/01M0G93XVGEMHY6NJA6X4Q3MAK/transcript` | VERIFIED — 3,573 segments, 571 KB in 0.047 s (data path leaves ~1.95 s of the 2 s budget for render) |
| Soak session summary exists with citations (Scenario 3 prerequisite) | VERIFIED — completed summary present |

### Browser walkthrough — PENDING

The in-browser pass (quickstart Scenarios 1–7) could not be run this
session: the browser-automation extension was not connected. The
recorder is left running at http://127.0.0.1:8377/ for the pass. To
record results, fill the table below (repeat Scenario 1 in Firefox,
NFR-004).

| Scenario | Target | Result |
|---|---|---|
| 1. Full meeting workflow (SC-001) | zero terminal commands | — |
| 2. Reconnect fidelity (SC-002) | reassembled == API record | — |
| 3. 5-hour fixture (SC-003/NFR-003) | open ≤ 2 s, smooth scroll, citation jumps | — |
| 4. Zero egress (SC-004) | all requests 127.0.0.1/localhost | — |
| 5. Layered honesty / capture-only (SC-005, T023) | no dead controls, remedies shown | — |
| 6. Resilience (FR-011, T020/T021) | disconnect banner + recovery; two tabs converge ≤ 1 poll tick; WS prefix replay in tab B | — |
| 7. State gallery (SC-006) | every state visually distinct | — |
| NFR-001 | list first render ≤ 1 s | — |
| NFR-002 | live segment on screen ≤ 1 s after emit | — |
