// Tiny DOM builder + formatters shared by every view (research R1's
// ~20-line helper; lives in its own module so views/ don't import app.js).

export function el(tag, ...args) {
  const [name, ...classes] = tag.split(".");
  const node = document.createElement(name || "div");
  if (classes.length) node.className = classes.join(" ");
  for (const a of args) {
    if (a == null) continue;
    if (typeof a === "string" || typeof a === "number") node.append(String(a));
    else if (a instanceof Node) node.append(a);
    else if (Array.isArray(a)) {
      for (const c of a) if (c != null) node.append(c);
    } else {
      for (const [k, v] of Object.entries(a)) {
        if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
        else if (v === true) node.setAttribute(k, "");
        else if (v !== false && v != null) node.setAttribute(k, v);
      }
    }
  }
  return node;
}

export function clear(node) {
  node.textContent = "";
  return node;
}

// seconds → hh:mm:ss (mono timestamps per ui-notes)
export function fmtClock(s) {
  s = Math.max(0, Math.floor(s));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return [h, m, s % 60].map((n) => String(n).padStart(2, "0")).join(":");
}

export function fmtDuration(s) {
  if (s == null) return "—";
  return fmtClock(s);
}

export function fmtBytes(n) {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let v = n;
  let u = -1;
  do {
    v /= 1024;
    u += 1;
  } while (v >= 1024 && u < units.length - 1);
  return `${v.toFixed(v >= 100 ? 0 : 1)} ${units[u]}`;
}

export function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}
