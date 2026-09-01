// Session view: header/controls (FR-004), transcript pane — live tail
// with honest lag and finalising → completed (FR-005), stored rendering
// with transcript states and the on-demand transcribe button
// (FR-006/FR-013) — plus citation jumps incl. superseded versions
// (FR-008, research R6). Hosts the summary and chat panes.

import { api, friendly } from "../api.js";
import { clear, el, fmtBytes, fmtClock, fmtDate, fmtDuration } from "../dom.js";
import { createVList } from "../vlist.js";
import { tailTranscript } from "../streams.js";
import { renderSummaryPane } from "./summary.js";
import { renderChatPane } from "./chat.js";

const STATE_CHIP = {
  live: ["good", "live"],
  finalising: ["warn", "finalising"],
  completed: ["good", "completed"],
  failed: ["critical", "failed"],
  interrupted_live: ["warn", "interrupted"],
  pending: ["warn", "transcribing"],
};

const STATUS_PILL = { completed: "good", interrupted: "warn", active: "critical" };

export async function renderSessionView(root, sessionId, state) {
  let session = await api.getSession(sessionId);
  let transcript = null; // current TranscriptResponse
  let items = []; // rendered segments, ordered
  let seqIndex = new Map(); // seq -> items index
  let cursor = -1; // last seq on screen — the reconnect cursor (R4)
  let tail = null;
  let tState = null;
  let tFinal = false;
  let lag = null;
  let transcriptError = null; // friendly refusal text (transcribe attempts)
  let noTranscript = false;
  let destroyed = false;
  let versionNumbers = null; // transcript id -> ordinal (for excerpt labels)

  // ---- DOM skeleton -----------------------------------------------------

  const headerPanel = el("div.panel");
  const transcriptPanel = el("div.panel");
  const transcriptHead = el("div.panel-head");
  const scroller = el("div.transcript-scroller");
  transcriptPanel.append(transcriptHead, scroller);
  const summaryPanel = el("div.panel");
  const chatPanel = el("div.panel");
  const left = el("div", transcriptPanel);
  const right = el("div", summaryPanel, chatPanel);
  root.append(headerPanel, el("div.session-grid", left, right));

  const vl = createVList(scroller, {
    render: (seg) =>
      el("div.seg." + seg.source,
        el("span.ts", fmtClock(seg.start_s)),
        el("span.who", seg.source),
        el("span.text", seg.text)),
  });
  vl.onFollow = () => renderTranscriptHead();

  // ---- header -----------------------------------------------------------

  let elapsedEl = null;

  function renderHeader() {
    clear(headerPanel);
    elapsedEl = null;
    const head = el("div.panel-head");
    head.append(
      el("a", { href: "#/" }, "← Sessions"),
      el("h2", session.title || "Untitled"),
      el("span.pill." + (STATUS_PILL[session.status] || "idle"), session.status),
    );
    if (session.status === "active") {
      elapsedEl = el("span.mono",
        fmtClock((Date.now() - new Date(session.started_at).getTime()) / 1000));
      head.append(el("span.rec-dot"), elapsedEl,
        el("button", "Stop", { onclick: stop }));
    } else {
      head.append(el("span.mono", fmtDuration(session.duration_s)));
    }
    head.append(el("span.hint",
      `${fmtDate(session.started_at)} · ${fmtBytes(session.size_bytes)}`));
    headerPanel.append(head);
    if (headerError) headerPanel.append(el("div.error-line", headerError));
  }

  let headerError = null;

  async function stop() {
    headerError = null;
    try {
      session = await api.stopSession(sessionId);
    } catch (e) {
      headerError = friendly(e);
    }
    renderHeader();
    // The stream's status frames carry finalising → completed (FR-005);
    // if there is no live stream (capture-only), just refresh once.
    if (!tail) refreshTranscript();
  }

  // ---- transcript pane --------------------------------------------------

  function renderTranscriptHead() {
    clear(transcriptHead);
    transcriptHead.append(el("h2", "Transcript"));
    if (tState) {
      const [cls, label] = STATE_CHIP[tState] || ["idle", tState];
      transcriptHead.append(el("span.chip." + cls, el("span.dot"), label));
    }
    if (tState === "live") {
      transcriptHead.append(el("span.chip.good", el("span.dot"),
        lag == null ? "live" : `live · lag ${Math.round(lag)} s`));
      if (!vl.isFollowing()) {
        transcriptHead.append(el("button.follow-chip", "↓ jump to live", {
          onclick: () => vl.refollow(),
        }));
      }
    }
    // On-demand progress: a queued/running pass on this or a pending transcript.
    const job = tState === "pending" ? transcript?.job : null;
    const pending = transcript?.pending_job || null;
    const prog = job || pending;
    if (prog && ["queued", "running", "finalising"].includes(prog.state)) {
      const frac = prog.total_chunks
        ? Math.min(1, (prog.progress_chunks || 0) / prog.total_chunks)
        : null;
      transcriptHead.append(
        el("span.hint", pending && transcript && tState !== "pending"
          ? "new version transcribing — current transcript stays below"
          : `transcribing (${prog.state})`),
        el("div.progress-track", { style: "flex:1;min-width:80px" },
          frac == null
            ? el("div.progress-fill.indeterminate")
            : el("div.progress-fill", { style: `width:${Math.round(frac * 100)}%` })),
      );
    }
    if (tState === "failed" && transcript?.job?.failure_reason) {
      transcriptHead.append(el("span.hint", transcript.job.failure_reason));
    }
    // Transcribe / re-transcribe where the API offers it (FR-013).
    if (session.status !== "active" && !prog) {
      const missingOrBroken =
        noTranscript || ["failed", "interrupted_live"].includes(tState);
      if (missingOrBroken) {
        if (state.transcription?.ready) {
          transcriptHead.append(el("button.primary", "Transcribe now", { onclick: transcribe }));
        }
      } else if (tState === "completed" && state.transcription?.ready) {
        transcriptHead.append(el("button", "Re-transcribe", { onclick: transcribe }));
      }
    }
  }

  function renderTranscriptBody() {
    if (noTranscript) {
      scroller.hidden = true;
      let msg = "No transcript for this session.";
      if (state.transcription && !state.transcription.ready) {
        msg += ` Transcription is ${state.transcription.status === "not_installed"
          ? "not installed" : "not ready"}${state.transcription.reason
          ? ` — ${state.transcription.reason}` : ""}.`;
      }
      if (!transcriptPanel.querySelector(".empty")) {
        transcriptPanel.append(el("div.empty", msg));
      } else {
        transcriptPanel.querySelector(".empty").textContent = msg;
      }
    } else {
      scroller.hidden = false;
      transcriptPanel.querySelector(".empty")?.remove();
    }
    if (transcriptError) {
      transcriptPanel.querySelector(".error-line")?.remove();
      transcriptPanel.append(el("div.error-line", transcriptError));
    } else {
      transcriptPanel.querySelector(".error-line")?.remove();
    }
  }

  async function transcribe() {
    transcriptError = null;
    try {
      await api.transcribe(sessionId);
    } catch (e) {
      transcriptError = friendly(e);
    }
    await refreshTranscript();
  }

  function adopt(t) {
    transcript = t;
    noTranscript = false;
    tState = t.state;
    tFinal = t.final;
    lag = t.job?.lag_s ?? null;
    items = t.segments.slice();
    seqIndex = new Map(items.map((s, i) => [s.seq, i]));
    cursor = items.length ? items[items.length - 1].seq : -1;
    vl.setItems(items);
    maybeStartTail();
    renderTranscriptHead();
    renderTranscriptBody();
  }

  function appendSegments(segs) {
    const fresh = segs.filter((s) => !seqIndex.has(s.seq));
    if (!fresh.length) return;
    for (const s of fresh) {
      seqIndex.set(s.seq, items.length);
      items.push(s);
      cursor = Math.max(cursor, s.seq);
    }
    vl.append(fresh);
  }

  function maybeStartTail() {
    const liveish = session.status === "active" || ["live", "finalising"].includes(tState);
    if (tail || destroyed || !liveish) return;
    if (!transcript && !state.transcription?.ready) return; // capture-only: nothing to tail
    vl.setFollowMode(true);
    tail = tailTranscript({
      sessionId,
      after: cursor,
      onSegment: (seg) => appendSegments([seg]),
      onStatus: (frame) => {
        tState = frame.state;
        lag = frame.lag_s;
        tFinal = frame.final;
        noTranscript = false;
        renderTranscriptHead();
        renderTranscriptBody();
      },
      onEnd: () => {
        tail = null;
        vl.setFollowMode(false);
        refreshTranscript(); // authoritative final state + job info
      },
    });
  }

  async function refreshTranscript() {
    let t;
    try {
      t = await api.getTranscript(sessionId, transcript ? cursor : -1);
    } catch (e) {
      if (e.code === "transcript_not_found") {
        noTranscript = true;
        renderTranscriptHead();
        renderTranscriptBody();
      }
      return;
    }
    if (destroyed) return;
    if (!transcript || t.id !== transcript.id) {
      adopt(transcript ? await api.getTranscript(sessionId) : t);
    } else {
      transcript.job = t.job;
      transcript.pending_job = t.pending_job;
      tState = t.state;
      tFinal = t.final;
      lag = t.job?.lag_s ?? lag;
      appendSegments(t.segments);
      renderTranscriptHead();
      renderTranscriptBody();
    }
  }

  // ---- citation jumps (FR-008, R6) --------------------------------------

  async function jumpToCitation(citation) {
    if (transcript && citation.transcript_id === transcript.id) {
      const idx = seqIndex.get(citation.seq);
      if (idx !== undefined) {
        vl.scrollToIndex(idx);
        transcriptPanel.scrollIntoView({ block: "nearest" });
        return;
      }
    }
    await showExcerpt(citation);
  }

  async function versionLabel(tid) {
    if (!versionNumbers) {
      try {
        const list = (await api.listTranscripts(sessionId)).transcripts
          .slice()
          .sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
        versionNumbers = new Map(list.map((t, i) => [t.id, i + 1]));
      } catch {
        versionNumbers = new Map();
      }
    }
    const n = versionNumbers.get(tid);
    return n ? `v${n}` : "an older version";
  }

  async function showExcerpt(citation) {
    let version;
    try {
      version = await api.getTranscriptVersion(sessionId, citation.transcript_id);
    } catch (e) {
      transcriptError = `Citation target unavailable: ${friendly(e)}`;
      renderTranscriptBody();
      return;
    }
    const label = await versionLabel(citation.transcript_id);
    const idx = version.segments.findIndex((s) => s.seq === citation.seq);
    const around = idx === -1
      ? []
      : version.segments.slice(Math.max(0, idx - 2), idx + 3);
    const backdrop = el("div.popover-backdrop");
    const pop = el("div.popover",
      el("button.close", "Close", { onclick: () => close() }),
      el("div.version-label", `Cited from transcript ${label} — superseded`),
      around.length
        ? around.map((s) =>
            el(s.seq === citation.seq ? `div.seg.${s.source}.cited` : `div.seg.${s.source}`,
              el("span.ts", fmtClock(s.start_s)),
              el("span.who", s.source),
              el("span.text", s.text)))
        : el("div.empty", "The cited segment no longer exists in that version."),
    );
    function close() {
      backdrop.remove();
      pop.remove();
      document.removeEventListener("keydown", onKey);
    }
    function onKey(ev) {
      if (ev.key === "Escape") close();
    }
    backdrop.addEventListener("click", close);
    document.addEventListener("keydown", onKey);
    document.body.append(backdrop, pop);
  }

  // ---- assemble ---------------------------------------------------------

  renderHeader();
  try {
    adopt(await api.getTranscript(sessionId));
  } catch (e) {
    noTranscript = true;
    tState = null;
    maybeStartTail(); // live session whose transcript hasn't been created yet
    renderTranscriptHead();
    renderTranscriptBody();
  }

  const panes = { onCitation: jumpToCitation, getSession: () => session,
    getTranscript: () => transcript };
  const summaryPane = await renderSummaryPane(summaryPanel, sessionId, state, panes);
  const chatPane = await renderChatPane(chatPanel, sessionId, state, panes);

  return {
    destroy() {
      destroyed = true;
      tail?.close();
      vl.destroy();
      summaryPane.destroy?.();
      chatPane.destroy?.();
    },
    async onPoll(st) {
      // Multi-tab convergence (R8): re-sync the session on every tick.
      const s = await api.getSession(sessionId).catch(() => null);
      if (destroyed) return;
      if (s) {
        const statusChanged = s.status !== session.status;
        session = s;
        if (statusChanged) {
          renderHeader();
          renderTranscriptHead();
        }
      }
      const jobActive =
        transcript?.pending_job || ["pending", "finalising"].includes(tState);
      if (!tail && (jobActive || (noTranscript && session.status === "active"))) {
        await refreshTranscript();
      }
      maybeStartTail();
      summaryPane.onPoll?.(st);
      chatPane.onPoll?.(st);
    },
    onTick() {
      if (elapsedEl && session.status === "active") {
        elapsedEl.textContent =
          fmtClock((Date.now() - new Date(session.started_at).getTime()) / 1000);
      }
      chatPane.onTick?.();
    },
  };
}
