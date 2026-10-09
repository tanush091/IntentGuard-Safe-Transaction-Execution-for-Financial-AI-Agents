"""
Export the gateway's OpenAPI schema to docs/api/openapi.json.

    python scripts/export_openapi.py           # write the file
    python scripts/export_openapi.py --check   # exit 1 if the committed file is out of date (CI)

The committed schema is what frontend/scripts/check-contract.mjs compares the dashboard's route
table against, and what docs/api.md is generated from, so it must track the code.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "api" / "openapi.json"


def render() -> str:
    sys.path.insert(0, str(ROOT / "backend"))
    from gateway_api.main import app

    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    text = render()
    if "--check" in sys.argv[1:]:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print(f"[FAIL] {OUT.relative_to(ROOT)} is out of date; run: python scripts/export_openapi.py")
            return 1
        print(f"[OK] {OUT.relative_to(ROOT)} matches the code")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"[INFO] Wrote {OUT.relative_to(ROOT)} ({len(json.loads(text)['paths'])} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
