"""
IntentGuard benchmark. Run from experiments/:  python -m bench run ...

The protocol packages (intentguard, paysim) live in backend/. Put that directory on sys.path so
the benchmark runs without installing anything; worker processes inherit the parent's sys.path.
"""

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if _BACKEND.is_dir() and str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
