#!/usr/bin/env python3
from __future__ import annotations

import shutil
import site
import sys
import sysconfig
from pathlib import Path

DIST_INFO_PATTERNS = [
    "protobuf-*.dist-info",
    "grpcio-*.dist-info",
    "grpcio_tools-*.dist-info",
    "google-*.dist-info",
]

EGG_INFO_PATTERNS = [
    "protobuf-*.egg-info",
    "grpcio-*.egg-info",
    "grpcio_tools-*.egg-info",
    "google-*.egg-info",
]

TOP_LEVEL_DIRS = [
    "grpc",
    "grpc_tools",
]

GOOGLE_SUBDIRS = [
    "protobuf",
]


def iter_site_packages() -> list[Path]:
    paths = []

    try:
        for p in site.getsitepackages():
            paths.append(Path(p))
    except Exception:
        pass

    try:
        paths.append(Path(site.getusersitepackages()))
    except Exception:
        pass

    cfg = sysconfig.get_paths()
    for key in ("purelib", "platlib"):
        value = cfg.get(key)
        if value:
            paths.append(Path(value))

    unique = []
    seen = set()
    for path in paths:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        if str(resolved) in seen:
            continue
        seen.add(str(resolved))
        unique.append(path)

    return unique


def remove_path(path: Path) -> None:
    if not path.exists():
        return

    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()

    print(f"removed: {path}")


def remove_google_subdirs(site_packages: Path) -> None:
    google_dir = site_packages / "google"
    if not google_dir.exists() or not google_dir.is_dir():
        return

    for name in GOOGLE_SUBDIRS:
        remove_path(google_dir / name)

    try:
        next(google_dir.iterdir())
    except StopIteration:
        remove_path(google_dir)


def clean_site_packages() -> None:
    site_packages_list = iter_site_packages()

    print(f"python: {sys.executable}")
    for site_packages in site_packages_list:
        print(f"scan: {site_packages}")

        if not site_packages.exists():
            continue

        for name in TOP_LEVEL_DIRS:
            remove_path(site_packages / name)

        remove_google_subdirs(site_packages)

        for pattern in DIST_INFO_PATTERNS:
            for path in site_packages.glob(pattern):
                remove_path(path)

        for pattern in EGG_INFO_PATTERNS:
            for path in site_packages.glob(pattern):
                remove_path(path)


if __name__ == "__main__":
    clean_site_packages()
