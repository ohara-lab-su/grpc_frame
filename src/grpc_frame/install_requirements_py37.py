#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    requirements_file = Path(__file__).resolve().parents[2] / "requirements-py37.txt"

    if not requirements_file.exists():
        raise FileNotFoundError(requirements_file)

    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-cache-dir",
        "--force-reinstall",
        "-r",
        str(requirements_file),
    ]

    print("running:")
    print(" ".join(cmd))
    subprocess.check_call(cmd)
