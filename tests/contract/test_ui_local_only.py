"""Contract: shipped UI files reference no non-loopback origin (FR-002).

Layer 1 of research R7's enforcement: scan every file shipped under
src/ambient_recorder/ui/ for absolute http(s)/ws(s) URLs and
protocol-relative (`//host`) asset references; only loopback hosts are
allowed. (Layers 2 and 3: the CSP response header, and the manual
devtools check in quickstart SC-004.)
"""

from __future__ import annotations

import re
from pathlib import Path

UI_DIR = Path(__file__).resolve().parents[2] / "src" / "ambient_recorder" / "ui"

# Absolute URL with a non-loopback host. A URL needs a host character after
# the scheme: a bare "ws://" literal concatenated with location.host (itself
# loopback — the recorder only binds loopback) is not an egress reference.
ABSOLUTE = re.compile(
    r"(?:https?|wss?)://(?!127\.0\.0\.1|localhost)[A-Za-z0-9\[]", re.IGNORECASE
)
# Protocol-relative references in markup/CSS (src="//…", href='//…', url(//…)).
PROTOCOL_RELATIVE = re.compile(
    r"""(?:src|href)\s*=\s*["']\s*//|url\(\s*["']?\s*//""", re.IGNORECASE
)


# Text assets are scanned line by line; binary assets (images) can't carry a
# loadable URL past the CSP, but keep them to a known set so nothing
# unexpected ships.
TEXT_SUFFIXES = {".html", ".css", ".js", ".svg", ".json", ".txt", ".md"}
BINARY_SUFFIXES = {".png", ".ico"}


def _shipped_files() -> list[Path]:
    return sorted(p for p in UI_DIR.rglob("*") if p.is_file())


def test_ui_directory_ships_the_shell():
    assert (UI_DIR / "index.html").is_file()
    assert (UI_DIR / "style.css").is_file()
    assert (UI_DIR / "js" / "app.js").is_file()


def test_only_known_asset_types_ship():
    unexpected = [
        str(p.relative_to(UI_DIR))
        for p in _shipped_files()
        if p.suffix.lower() not in TEXT_SUFFIXES | BINARY_SUFFIXES
    ]
    assert not unexpected, f"unexpected asset types shipped: {unexpected}"


def test_no_non_loopback_urls_in_shipped_ui_files():
    offenders: list[str] = []
    for path in _shipped_files():
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if ABSOLUTE.search(line) or PROTOCOL_RELATIVE.search(line):
                offenders.append(f"{path.relative_to(UI_DIR)}:{lineno}: {line.strip()}")
    assert not offenders, "non-loopback references in shipped UI files:\n" + "\n".join(offenders)
