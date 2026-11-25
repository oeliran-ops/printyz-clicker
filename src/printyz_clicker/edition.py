"""Which edition is running: "developer" (default) or "customer".

The customer build ships an `edition.json` ({"edition": "customer"}) and `customer_policy.json`
next to the program; nothing in the customer UI can switch to developer mode.
"""

from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path


def app_root() -> Path:
    """Folder that holds edition.json / customer_policy.json (frozen exe dir, or the repository)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def policy_path() -> Path:
    if getattr(sys, "frozen", False):
        return app_root() / "customer_policy.json"
    return app_root() / "customer" / "customer_policy.json"


@lru_cache(maxsize=1)
def edition() -> str:
    env = os.environ.get("PRINTYZ_EDITION")
    if env in ("customer", "developer"):
        return env
    f = app_root() / "edition.json"
    if f.exists():
        try:
            if json.loads(f.read_text("utf-8")).get("edition") == "customer":
                return "customer"
        except Exception:  # noqa: BLE001
            pass
    return "developer"


def is_customer() -> bool:
    return edition() == "customer"
