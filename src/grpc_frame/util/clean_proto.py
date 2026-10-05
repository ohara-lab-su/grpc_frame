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
    util_dir = Path(__file__).resolve().parent
    frame_dir = util_dir.parent
    repo_root = frame_dir.parents[1]

    files = [
        frame_dir / "ctrl_pb2.py",
        frame_dir / "ctrl_pb2_grpc.py",
        frame_dir / "events_pb2.py",
        frame_dir / "events_pb2_grpc.py",
    ]

    dirs = [
        repo_root / "build",
        repo_root / "dist",
        repo_root / "src" / "grpc_frame.egg-info",
        frame_dir / "__pycache__",
        util_dir / "__pycache__",
    ]

    for path in files:
        remove_file(path)

    for path in dirs:
        remove_dir(path)
