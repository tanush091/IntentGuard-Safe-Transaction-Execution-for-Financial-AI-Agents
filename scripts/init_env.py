"""
Create .env from .env.example (if missing), add settings that .env.example gained since, and fill in
empty secrets with random values.

    python scripts/init_env.py

Secrets are generated locally and never leave the machine; .env is gitignored. Existing values are
not touched.
"""

from __future__ import annotations

import re
import secrets
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRETS = ("JWT_SECRET", "WEBHOOK_SECRET")


def main() -> None:
    env, example = ROOT / ".env", ROOT / ".env.example"
    if not env.exists():
        shutil.copyfile(example, env)
        print("[INFO] Created .env from .env.example")
    text = env.read_text(encoding="utf-8")
    # Settings added to .env.example since this .env was created (e.g. SIMULATOR_MODE after an upgrade)
    # are appended with their example values; existing values are never changed.
    present = set(re.findall(r"(?m)^([A-Z][A-Z0-9_]*)=", text))
    added = [line for line in example.read_text(encoding="utf-8").splitlines()
             if (m := re.match(r"([A-Z][A-Z0-9_]*)=", line)) and m.group(1) not in present]
    if added:
        text = text.rstrip("\n") + "\n\n# Added by scripts/init_env.py from .env.example\n" + "\n".join(added) + "\n"
        print(f"[INFO] Added to .env: {', '.join(line.split('=', 1)[0] for line in added)}")
    for key in SECRETS:
        if re.search(rf"(?m)^{key}=\s*$", text):
            text = re.sub(rf"(?m)^{key}=\s*$", f"{key}={secrets.token_urlsafe(48)}", text)
            print(f"[INFO] Generated {key} in .env")
        elif not re.search(rf"(?m)^{key}=", text):
            text = text.rstrip("\n") + f"\n{key}={secrets.token_urlsafe(48)}\n"
            print(f"[INFO] Added {key} to .env")
    env.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
