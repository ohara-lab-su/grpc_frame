#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path


def remove_file(path: Path) -> None:
    if path.exists():
        path.unlink()
        print(f"removed: {path}")


def remove_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
        print(f"removed: {path}")


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    repo_root = here.parents[1]

    files = [
        here / "ctrl_pb2.py",
        here / "ctrl_pb2_grpc.py",
        here / "events_pb2.py",
        here / "events_pb2_grpc.py",
    ]

    dirs = [
        repo_root / "build",
        repo_root / "dist",
        repo_root / "src" / "grpc_frame.egg-info",
        here / "__pycache__",
    ]

    for path in files:
        remove_file(path)

    for path in dirs:
        remove_dir(path)
