"""Download Whisper (CTranslate2) model weights into data/models/<name>/.

Usage: python scripts/fetch_models.py medium [distil-large-v3 ...]

Constitution gate (c): this pulls ~1.5 GB per model from Hugging Face.
Run deliberately, never at recorder runtime (research R8). Uses the HF
token from ~/.transcribe.env (HF_TOKEN=...) if present, for gated repos.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = REPO_ROOT / "data" / "models"


def _load_token() -> str | None:
    env = Path.home() / ".transcribe.env"
    if env.is_file():
        for line in env.read_text().splitlines():
            if line.startswith("HF_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"')
    return os.environ.get("HF_TOKEN")


def main(names: list[str]) -> int:
    from faster_whisper.utils import download_model

    if not names:
        print(__doc__)
        return 2
    token = _load_token()
    if token:
        os.environ.setdefault("HF_TOKEN", token)  # huggingface_hub reads this
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for name in names:
        target = MODELS_DIR / name
        print(f"fetching {name} -> {target} ...", flush=True)
        path = download_model(name, output_dir=str(target))
        size = sum(p.stat().st_size for p in Path(path).rglob("*") if p.is_file())
        print(f"  ok: {size / 1e6:.0f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
