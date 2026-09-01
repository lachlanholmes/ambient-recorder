# Feature 004 — Web UI validation record

Protocol: `specs/004-web-ui/quickstart.md` (Scenarios 1–7), performance
targets NFR-001/002/003, egress check SC-004.

## Run 2026-09-01 — implementation session

Environment: recorder from source (editable install), real data root,
transcription ready (`medium/int8_float16/cuda`), assistant ready
(ollama 0.32.15, phi4-mini). Browser pass driven over the Chrome
DevTools Protocol against real Chrome 152 (separate scratch profile);
Firefox pass over WebDriver BiDi against the installed Firefox
(headless). The live meeting used Windows TTS through the speakers as
the "them" track (session `01M1FAMMXBBM2ES3D2V0KCW227`, kept in the
archive).

### Contract / static layer

| Check | Result |
|---|---|
| Serving contract (`/` + CSP + no-cache index, mount-order guard, missing-ui degradation, OpenAPI surface unchanged) | **PASS** — `tests/contract/test_ui_serving.py` |
| Local-only assets (text scan + known-binary allowlist) | **PASS** — `tests/contract/test_ui_local_only.py` |
| Full regression (001–003 suites) | **PASS** — 222 tests |

### Browser walkthrough

| Scenario | Target | Result |
|---|---|---|
| 1. Full meeting workflow (SC-001) | zero terminal commands | **PASS** — readiness chips → titled start → live transcript (me/them, timestamps, `live · lag N s` chip) → live ask (streamed answer, citation, `live … segment 40` watermark) → stop → completed → Generate summary (progress → structured render) → summary citation jump → follow-up ask in the same conversation (`final` watermark) |
| 2. Reconnect fidelity (SC-002) | reassembled == API record | **PASS** — mid-meeting reload: 41/41 segments, set-identical, zero gaps, zero duplicates. Note: rows near overlapping speech can display in arrival order on the live tail vs spoken order in the stored sort; the set is always identical and reconciles on reload |
| 3. 5-hour fixture (SC-003/NFR-003) | open ≤ 2 s, smooth scroll, citation jumps | **PASS** — 3,573 segments / 571 KB; API fetch 0.047 s; first rows at **1.47 s** from navigation; windowed DOM held ~120 nodes; 21-hop full-range scroll sweep ran at 2 frames/hop (~60 fps, max gap 34 ms); JS heap 2 MB; summary citation jump scrolled to offset ~96 k and highlighted the exact cited segment |
| 4. Zero egress (SC-004) | all requests loopback | **PASS** — full-workflow CDP network audit: 220+ requests, every host `127.0.0.1:8377`; CSP response header additionally blocks any non-loopback load |
| 5. Layered honesty / capture-only (SC-005, T023) | no dead controls, remedies shown | **PASS** — scratch data root, no models, dead Ollama URL: chips show `not ready`/`not installed` with the API's remedy text; record→stop fully works; live transcript attempt renders `failed` + `engine_not_ready: model_missing…`; transcribe button correctly withheld while not ready; zero WS attempts; zero console errors |
| 6. Resilience (FR-011, T020/T021) | banner + recovery; tabs converge; prefix replay | **PASS** — kill: “Recorder disconnected — retrying in N s” + dimming; restart: recovered with no reload (rows + summary intact). Two tabs on the live session showed identical rows; stop clicked in tab B; tab A converged on its next visible poll tick (hidden tabs pause polling by design and catch up on focus) |
| 7. State gallery (SC-006) | states visually distinct | **PASS** — interrupted session (warn pill); declined answer (idle bubble, “Not discussed in this meeting.”); ungrounded (warn `unverified` tag); interrupted answer (warn tag + preserved 119-char partial; fabricated live by killing the recorder mid-stream); no-transcript legacy session → `Transcribe now` → queued → running → completed (the kill-test audio genuinely has zero speech; UI renders the empty truth); re-summary pending shows progress with the readable summary kept (observed during generation). Failed-transcript render shares the same state-chip path as capture-only’s `failed` (verified there) |
| NFR-001 | list first render ≤ 1 s | **PASS** — 33/57/49 ms over three loads (MutationObserver-stamped) |
| NFR-002 | live segment ≤ 1 s after emit | **PASS** — sampled DOM row count vs API segment count every 1.5 s across the live meeting: never behind at any sample |
| NFR-004 | Firefox | **PASS** (render + interaction level) — list, readiness chips, windowed soak transcript, summary, citation jump + highlight, via WebDriver BiDi; full meeting flow exercised in Chromium |

### Bugs found by this pass (all fixed in-session)

1. **dom.js dangling-else** — the attrs/onclick branch of `el()` bound to
   the `if` inside the array loop, so every attribute and event listener
   was silently dropped. Braced the chain. (Found via citation-jump
   failure; also restored hrefs, input attrs, all buttons.)
2. **Boot ordering** — first render was gated on the readiness probes
   (VRAM/Ollama), 1.3 s. List now renders from the session fetch alone;
   readiness fills in as it lands. 33–57 ms.
3. **Stale transcript state after stop** — `transcript.state/.final`
   weren't updated from WS status frames / refreshes, so the summary
   pane never offered Generate. Synced.
4. **Capture-only tail loop** — the live view tailed a `failed`
   transcript on an active session, hammering refused WS handshakes on
   a 10 s backoff loop. Tail now requires a live/finalising/pending
   transcript.
5. **Favicon CSP violation** — `data:` favicon tripped
   `default-src 'self'`; replaced with a shipped `/favicon.png`.

### Notes

- Chrome logs expected API 404s (e.g. `transcript_not_found` for
  001-era sessions probed by the list's transcript-state chips) as
  console errors at the network layer; these are refusals the UI
  handles, not JS errors.
- Live-view row order near overlapping speech follows stream arrival
  (seq) until a reload re-sorts by spoken time — same set either way
  (see Scenario 2).
- Pre-existing suite flake (not 004):
  `test_engine_failure_does_not_touch_recording` intermittently times
  out under full-suite load; reproduced identically on pre-004 commit
  73bca8b, passes in isolation.
