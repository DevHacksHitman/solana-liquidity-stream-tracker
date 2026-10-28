"""Quick environment check: interpreter and Python version."""

import sys

print("--- Python environment check ---")
print(f"Python version: {sys.version}")
print(f"Interpreter path: {sys.executable}")
print(
    "Virtual env active: "
    f"{hasattr(sys, 'real_prefix') or (sys.base_prefix != sys.prefix)}"
)
print("--------------------------------")

if sys.version_info >= (3, 10):
    print("OK: Python 3.10 or higher.")
    sys.exit(0)
print("Warning: Python 3.10+ recommended.")
sys.exit(1)
