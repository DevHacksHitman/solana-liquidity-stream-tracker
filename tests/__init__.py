"""Test package: keeps the repo root importable under any discovery mode."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
