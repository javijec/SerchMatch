"""Local launcher for the Streamlit application."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Run the Streamlit app."""
    app_path = Path(__file__).resolve().parent / "app" / "streamlit_app.py"
    command = [sys.executable, "-m", "streamlit", "run", str(app_path)]
    completed = subprocess.run(command, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
