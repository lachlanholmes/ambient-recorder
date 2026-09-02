// Boot, hash routing, visible-tab poll loop, disconnect banner, and the
// readiness header (FR-003, FR-011, research R5).
//
// Polling: while the tab is visible, health + the three readiness
// endpoints every 3 s and the session list every 5 s; everything pauses
// on document.hidden. A failed health poll flips the "recorder
// disconnected" banner; the first success after that re-bootstraps every
// panel (recorder restarts recover without a reload).

import { api } from "./api.js";
import { clear, el, fmtClock } from "./dom.js";
import { renderSessionsView } from "./views/sessions.js";
import { renderSessionView } from "./views/session.js";

const POLL_FAST_MS = 3000; // health + readiness
const POLL_LIST_MS = 5000; // session list

export const state = {
  connected: true,
  health: null,
  devices: null,
  transcription: null,
  assistant: null,
  sessions: [],
  activeSession: null, // SessionDetail of the active session, for the banner
};

let currentView = null;
let disconnectedSince = 0;
let nextRetryAt = 0;

// ---- routing --------------------------------------------------------------

function route() {
  const m = (location.hash || "#/").match(/^#\/session\/([A-Za-z0-9-]+)/);
  return m ? { name: "session", id: m[1] } : { name: "list" };
}

async function renderRoute() {
  if (currentView?.destroy) currentView.destroy();
  currentView = null;
  const viewEl = clear(document.getElementById("view"));
  const r = route();
  try {
    currentView =
      r.name === "session"
        ? await renderSessionView(viewEl, r.id, state)
        : await renderSessionsView(viewEl, state);
  } catch (e) {
    viewEl.append(el("div.error-line", `Failed to load view: ${e.message}`));
  }
}

// ---- readiness header (T009 / FR-003) -------------------------------------

function chip(cls, label, remedy) {
  const c = el("span.chip." + cls, el("span.dot"), label);
  if (remedy) c.append(el("span.remedy", ` — ${remedy}`));
  return c;
}

function renderReadiness() {
  const host = clear(document.getElementById("readiness"));
  const d = state.devices;
  if (d) {
    if (d.ready) {
      host.append(chip("good", "Devices: ready"));
    } else {
      const missing = d.sources
        .filter((s) => s.status === "missing")
        .map((s) => s.kind)
        .join(", ");
      host.append(chip("critical", `Devices: ${missing || "unknown"} missing`,
        "reconnect or enable the device"));
    }
  } else {
    host.append(chip("idle", "Devices: …"));
  }
  host.append(layerChip("Transcription", state.transcription));
  host.append(layerChip("Assistant", state.assistant));
}

function layerChip(name, r) {
  if (!r) return chip("idle", `${name}: …`);
  if (r.ready) return chip("good", `${name}: ready${r.model ? ` (${r.model})` : ""}`);
  if (r.status === "not_installed") {
    return chip("idle", `${name}: not installed`, r.reason || "install to enable this layer");
  }
  return chip("warn", `${name}: not ready`, r.reason || "see logs");
}

// ---- active-session banner ------------------------------------------------

function renderActiveBanner() {
  const banner = document.getElementById("active-banner");
  const active = state.activeSession;
  if (!active || active.status !== "active") {
    banner.hidden = true;
    return;
  }
  const elapsed = (Date.now() - new Date(active.started_at).getTime()) / 1000;
  clear(banner).append(
    el("span.rec-dot"),
    el("a", { href: `#/session/${active.id}` }, `Recording: ${active.title || "Untitled"}`),
    el("span.mono", fmtClock(elapsed)),
  );
  banner.hidden = false;
}

async function syncActiveSession() {
  const id = state.health?.active_session_id;
  if (!id) {
    state.activeSession = null;
    return;
  }
  if (state.activeSession?.id !== id) {
    try {
      state.activeSession = await api.getSession(id);
    } catch {
      state.activeSession = null;
    }
  }
}

// ---- disconnect banner (FR-011) -------------------------------------------

function renderDisconnected() {
  const banner = document.getElementById("disconnect-banner");
  if (state.connected) {
    banner.hidden = true;
    document.body.classList.remove("disconnected");
    return;
  }
  const secs = Math.max(0, Math.ceil((nextRetryAt - Date.now()) / 1000));
  banner.textContent = `Recorder disconnected — retrying${secs ? ` in ${secs} s` : "…"}`;
  banner.hidden = false;
  document.body.classList.add("disconnected");
}

// ---- poll loop (R5) -------------------------------------------------------

async function pollFast() {
  if (document.hidden) return;
  nextRetryAt = Date.now() + POLL_FAST_MS;
  let health;
  try {
    health = await api.health();
  } catch {
    if (state.connected) {
      state.connected = false;
      disconnectedSince = Date.now();
    }
    renderDisconnected();
    return;
  }
  const wasDisconnected = !state.connected;
  state.connected = true;
  state.health = health;
  renderDisconnected();

  const [devices, transcription, assistant] = await Promise.allSettled([
    api.devices(),
    api.transcriptionReadiness(),
    api.assistantReadiness(),
  ]);
  if (devices.status === "fulfilled") state.devices = devices.value;
  if (transcription.status === "fulfilled") state.transcription = transcription.value;
  if (assistant.status === "fulfilled") state.assistant = assistant.value;
  renderReadiness();
  await syncActiveSession();
  renderActiveBanner();

  if (wasDisconnected) {
    // First success after an outage: re-bootstrap every panel (FR-011).
    await pollList(true);
    await renderRoute();
    return;
  }
  currentView?.onPoll?.(state);
}

async function pollList(force = false) {
  if ((document.hidden || !state.connected) && !force) return;
  try {
    state.sessions = (await api.listSessions()).sessions;
    currentView?.onSessions?.(state);
  } catch { /* transient; the fast poll owns disconnect handling */ }
}

// ---- boot -----------------------------------------------------------------

function tick1s() {
  renderActiveBanner();
  if (!state.connected) renderDisconnected();
  currentView?.onTick?.(state);
}

window.addEventListener("hashchange", renderRoute);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    pollFast();
    pollList();
  }
});

// Boot: the route renders as soon as the session list arrives (NFR-001);
// readiness probes (VRAM, Ollama) can take longer and fill in as they land.
renderReadiness();
pollList(true).then(renderRoute);
pollFast();
setInterval(pollFast, POLL_FAST_MS);
setInterval(pollList, POLL_LIST_MS);
setInterval(tick1s, 1000);
