#!/usr/bin/env python3
"""Dependency verification for the tracker.

Checks that the packages the listener needs import cleanly, verifies the
standard-library modules it relies on, and prints a short report. Exit
code 0 means the environment is ready.
"""

import importlib.util
import sys

REQUIRED = [
    # (distribution name, import name)
    ("websockets", "websockets"),
]

STDLIB = [
    "asyncio",
    "json",
    "sqlite3",
    "urllib.request",
]


def module_available(import_name: str) -> bool:
    try:
        return importlib.util.find_spec(import_name) is not None
    except (ImportError, ValueError):
        return False


def main() -> int:
    print("--- dependency check ---")
    ok = True
    for distribution, import_name in REQUIRED:
        present = module_available(import_name)
        ok = ok and present
        state = "OK" if present else f"MISSING (pip install {distribution})"
        print(f"{distribution}: {state}")

    print("--- stdlib ---")
    for import_name in STDLIB:
        state = "OK" if module_available(import_name) else "MISSING"
        print(f"{import_name}: {state}")

    if sys.version_info < (3, 10):
        print("Python 3.10+ required (IsolatedAsyncioTestCase, asyncio.to_thread).")
        ok = False

    print(f"--- result: {'OK' if ok else 'INCOMPLETE'} ---")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
