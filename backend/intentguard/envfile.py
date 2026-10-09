"""
Load `.env` files into the process environment.

Settings read with os.getenv (LLM_*, PAYSIM_*, SIMULATOR_MODE, ...) would otherwise ignore `.env`.
A `.env` in the working directory is loaded first, then the repository-root `.env`. A variable that
is already set (in the environment, or by the first file) is never overridden, so the environment
wins over the working-directory file, which wins over the root file.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]  # backend/intentguard/envfile.py -> repository root

_loaded = False


def load_env() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    for path in (Path.cwd() / ".env", REPO_ROOT / ".env"):
        if path.is_file():
            load_dotenv(path, override=False)  # earlier files win because nothing is overridden
