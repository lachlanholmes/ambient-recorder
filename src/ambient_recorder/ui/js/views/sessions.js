// Session list view (FR-006) + start controls (FR-004).
// Newest-first list with title, date, duration, size, status pill and
// transcription state; start with optional title, refusals rendered in
// plain language from the error envelope.

import { api, friendly } from "../api.js";
import { clear, el, fmtBytes, fmtClock, fmtDate, fmtDuration } from "../dom.js";

// session id -> transcript-state chip data; refreshed for non-terminal states
const transcriptCache = new Map();

const STATUS_PILL = {
  completed: "good",
  interrupted: "warn",
  active: "critical",
};

const TRANSCRIPT_CHIP = {
  live: ["good", "live"],
  finalising: ["warn", "finalising"],
  completed: ["good", "transcribed"],
  failed: ["critical", "transcript failed"],
  interrupted_live: ["warn", "transcript interrupted"],
  pending: ["warn", "transcribing"],
};

export async function renderSessionsView(root, state) {
  let destroyed = false;
  let startError = null;
  let busy = false;

  const startPanel = el("div.panel");
  const listPanel = el("div.panel");
  root.append(startPanel, listPanel);

  // ---- start / stop controls (FR-004) ----------------------------------

  let lastStartKey = null;

  function renderStart() {
    const activeId = state.health?.active_session_id || null;
    const key = `${activeId}|${busy}|${startError || ""}`;
    // Idle panel unchanged: skip the re-render so the title box keeps
    // the user's text and focus across poll ticks.
    if (!activeId && key === lastStartKey) return;
    lastStartKey = key;
    const prevInput = startPanel.querySelector(".start-row input");
    const prevTitle = prevInput ? prevInput.value : "";
    const hadFocus = prevInput != null && document.activeElement === prevInput;
    clear(startPanel);
    startPanel.append(el("h2", "Record"));
    if (activeId) {
      const active = state.activeSession;
      const elapsed = active
        ? fmtClock((Date.now() - new Date(active.started_at).getTime()) / 1000)
        : "";
      startPanel.append(
        el("div.toolbar",
          el("span.rec-dot"),
          el("a", { href: `#/session/${activeId}` },
            `Recording: ${active?.title || "Untitled"}`),
          el("span.mono", elapsed),
          el("button", "Stop", {
            disabled: busy,
            onclick: () => act(() => api.stopSession(activeId)),
          }),
        ),
      );
    } else {
      const input = el("input", { type: "text", placeholder: "Session title (optional)",
        maxlength: "200" });
      input.value = prevTitle;
      input.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") start(input.value);
      });
      startPanel.append(
        el("div.start-row",
          input,
          el("button.primary", "Start recording", {
            disabled: busy,
            onclick: () => start(input.value),
          }),
        ),
      );
      if (hadFocus) input.focus();
    }
    if (startError) startPanel.append(el("div.error-line", startError));
  }

  async function act(fn) {
    busy = true;
    startError = null;
    renderStart();
    try {
      await fn();
      await refreshNow();
    } catch (e) {
      startError = friendly(e);
    }
    busy = false;
    renderStart();
  }

  function start(title) {
    act(async () => {
      const detail = await api.createSession(title.trim());
      location.hash = `#/session/${detail.id}`;
    });
  }

  async function refreshNow() {
    try {
      state.health = await api.health();
      state.sessions = (await api.listSessions()).sessions;
      if (state.health.active_session_id) {
        state.activeSession = await api.getSession(state.health.active_session_id);
      } else {
        state.activeSession = null;
      }
    } catch { /* poll loop will catch up */ }
    renderList();
  }

  // ---- list (FR-006) ----------------------------------------------------

  function transcriptCell(s) {
    const cell = el("td");
    const cached = transcriptCache.get(s.id);
    const stale = !cached || s.status === "active" ||
      ["live", "finalising", "pending"].includes(cached.state);
    if (cached) {
      const [cls, label] = TRANSCRIPT_CHIP[cached.state] || ["idle", cached.state];
      cell.append(el("span.pill." + cls, label));
    } else {
      cell.append(el("span.hint", "…"));
    }
    if (stale) {
      // Lazy per-row fetch with a huge cursor: state only, zero segments.
      api.getTranscript(s.id, 999999999).then(
        (t) => {
          const pending = t.pending_job ? "pending" : null;
          transcriptCache.set(s.id, { state: pending || t.state });
          if (!destroyed && !cached) renderList();
        },
        () => transcriptCache.set(s.id, { state: "none" }),
      );
    }
    if (cached?.state === "none") {
      clear(cell).append(el("span.pill.idle", "no transcript"));
    }
    return cell;
  }

  function renderList() {
    clear(listPanel);
    listPanel.append(el("h2", "Sessions"));
    const sessions = state.sessions
      .slice()
      .sort((a, b) => new Date(b.started_at) - new Date(a.started_at));
    if (!sessions.length) {
      listPanel.append(el("div.empty", "No sessions yet — start your first recording above."));
      return;
    }
    const rows = sessions.map((s) => {
      const pill = el("span.pill." + (STATUS_PILL[s.status] || "idle"), s.status);
      const statusCell = el("td", pill);
      if (s.status === "active") {
        statusCell.prepend(el("span.rec-dot"), " ");
      }
      const tr = el("tr.row",
        el("td", el("a", { href: `#/session/${s.id}` }, s.title || "Untitled")),
        el("td.mono", fmtDate(s.started_at)),
        el("td.mono", s.status === "active"
          ? fmtClock((Date.now() - new Date(s.started_at).getTime()) / 1000)
          : fmtDuration(s.duration_s)),
        el("td.mono", fmtBytes(s.size_bytes)),
        statusCell,
        transcriptCell(s),
      );
      tr.addEventListener("click", (ev) => {
        if (ev.target.closest("a")) return;
        location.hash = `#/session/${s.id}`;
      });
      return tr;
    });
    listPanel.append(
      el("table.sessions",
        el("thead", el("tr",
          el("th", "Title"), el("th", "Started"), el("th", "Duration"),
          el("th", "Size"), el("th", "Status"), el("th", "Transcript"))),
        el("tbody", rows),
      ),
    );
  }

  renderStart();
  renderList();

  return {
    destroy() {
      destroyed = true;
    },
    onPoll() {
      renderStart();
    },
    onSessions() {
      renderList();
    },
    onTick() {
      if (state.health?.active_session_id) {
        renderStart();
        renderList();
      }
    },
  };
}
