#!/usr/bin/env python
"""
Build hook for grpc_frame.

Generate gRPC Python modules from ctrl.proto and events.proto immediately
before setuptools copies Python modules into the build directory.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Callable

from setuptools import setup
from setuptools.command.build_py import build_py


ROOT_DIR = Path(__file__).resolve().parent
BUILD_PROTO_PATH = ROOT_DIR / "src" / "grpc_frame" / "util" / "build_proto.py"


def load_build_proto() -> Callable[..., None]:
    spec = importlib.util.spec_from_file_location(
        "grpc_frame_build_proto",
        str(BUILD_PROTO_PATH),
    )
    if spec is None:
        raise RuntimeError("cannot load build_proto.py")

    if spec.loader is None:
        raise RuntimeError("cannot load build_proto.py")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    build_proto = getattr(module, "build_proto", None)
    if build_proto is None:
        raise RuntimeError("build_proto() is not defined")

    return build_proto


class BuildPy(build_py):
    def run(self) -> None:
        build_proto = load_build_proto()

        build_proto(proto_name="ctrl")
        build_proto(proto_name="events")

        super().run()


setup(
    cmdclass={
        "build_py": BuildPy,
    },
)
