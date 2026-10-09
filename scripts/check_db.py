"""
Move an incompatible local SQLite database aside before the gateway starts (called by start.bat).

    python scripts/check_db.py

The gateway refuses to start on a database created by an earlier schema (SchemaMismatch). For the
local SQLite file that start.bat uses, this script renames such a database to
`<name>.schema-<old>-<timestamp>.bak` instead, together with the simulator's state file: the two
stores describe the same payments and must start fresh together, or the first matching run reports
stale mismatches. Nothing is deleted. PostgreSQL databases are left alone (the gateway reports them).
"""

from __future__ import annotations

import os
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from intentguard.envfile import load_env  # noqa: E402
from intentguard.models import SCHEMA_VERSION  # noqa: E402

LEGACY_TABLES = {"operators", "proposals", "attempts", "audit_events"}


def sqlite_path(url: str) -> Path | None:
    if not url.startswith("sqlite:///"):
        return None
    path = Path(url[len("sqlite:///"):])
    return path if path.is_absolute() else BACKEND / path  # the gateway runs from backend/


def schema_of(db: Path) -> str | None:
    """The stored schema version, "legacy" for a pre-versioning database, None if empty or current."""
    with closing(sqlite3.connect(db)) as c:  # closed, not just committed: Windows locks open files
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not tables:
            return None
        version = None
        if "schema_meta" in tables:
            row = c.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
            version = row[0] if row else None
    if tables & LEGACY_TABLES:
        return version or "legacy"
    if "intents" in tables and version != SCHEMA_VERSION:
        return version or "unknown"
    return None


def move_aside(path: Path, tag: str) -> None:
    for p in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
        if p.exists():
            target = p.with_name(f"{p.name}.{tag}.bak")
            p.rename(target)
            print(f"[INFO] Moved {p.name} -> {target.name} (in {p.parent})")


def main() -> int:
    os.chdir(BACKEND)
    load_env()
    db = sqlite_path(os.environ.get("DATABASE_URL", "sqlite:///./intentguard_gateway.db"))
    if db is None or not db.exists():
        return 0
    old = schema_of(db)
    if old is None:
        return 0
    tag = f"schema-{old}-{time.strftime('%Y%m%d-%H%M%S')}"
    print(f"[INFO] {db.name} was created by an earlier IntentGuard (schema {old}, need {SCHEMA_VERSION}); "
          "starting with a fresh database. The old files are kept as backups.")
    move_aside(db, tag)
    state = Path(os.environ.get("PAYSIM_STATE_PATH", "paysim_state.json"))
    move_aside(state if state.is_absolute() else BACKEND / state, tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
