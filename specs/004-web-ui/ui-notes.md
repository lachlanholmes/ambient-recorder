# UI Design Notes (gate-b approved direction)

The visual direction approved at gate (b) via the UI-states mockup
slideshow, captured in-repo so T005 needs no external reference. These
are defaults, not law — implementation may adjust for legibility, but
departures from the me/them distinction or the honest-state rendering
need a reason.

## Palette

| Token | Value | Use |
|---|---|---|
| app ground | `#F6F7F9` | page background |
| panel | `#FFFFFF` | cards/panes, 1px border `#DDE3EA` |
| ink / muted | `#1C2733` / `#5C6B7A` | text / secondary text |
| **me** | `#2563EB` on `#EAF1FE` | my speech, primary buttons, citation chips |
| **them** | `#7A6A58` on `#F1ECE5` | other-party speech |
| good | `#1B7F4E` on `#E3F3EA` | ready, completed, live-ok |
| warn | `#A16207` on `#FCF3DF` | interrupted, ungrounded, regenerating |
| critical | `#B3261E` on `#FBEAE8` | recording dot, failed, disconnected banner |
| idle | `#6B7684` on `#ECEFF3` | not-installed layers, declined answers |

Semantic colors are distinct from the me-blue accent and never reused
for it.

## Typography

- UI text: system stack (`"Segoe UI", system-ui, sans-serif`) — the UI
  ships zero fonts (constitution I / FR-002).
- Timestamps, IDs, durations, counts: `Consolas, ui-monospace` with
  `font-variant-numeric: tabular-nums`.

## Components (as mocked)

- **Readiness chips** (header, right): pill + status dot per layer,
  e.g. `● Transcription: ready (medium)`; unavailable layers show the
  remedy inline in their panel, not just the chip.
- **Status pills** on sessions: completed=good, interrupted=warn,
  recording=critical dot + elapsed mono timer.
- **Transcript row**: `[hh:mm:ss] [me|them chip] text` — chip colored
  per speaker, timestamp mono/muted, cited row highlight = `#FFF6D9`
  with `#E8C34A` outline.
- **Lag chip** on live view: `live · lag N s` (good style); auto-follow
  indicator that disengages on scroll-up.
- **Citations**: `[n]` chips in me-blue; superseded-version excerpt
  popover carries an uppercase warn-colored label ("Cited from
  transcript v1 — superseded").
- **Honest states**: declined = idle-styled normal answer ("That wasn't
  discussed…"); ungrounded = warn "unverified" tag; failed = critical
  tag + reason + retry button; re-summary pending = progress bar with
  the old summary kept readable below.
- **Disconnected**: critical banner "Recorder disconnected — retrying
  in N s", content dimmed (~45% opacity), recovers without reload.

## Reference states (the 8 mockup artboards)

1 Home/list+readiness · 2 Live transcript · 3 Live ask · 4 Ended with
summary · 5 Citation jump (+superseded popover) · 6 Failure gallery ·
7 Capture-only remedies · 8 Disconnected.
