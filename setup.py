"""Generate gRPC modules as part of the setuptools wheel build."""

import importlib.util
from pathlib import Path
from setuptools import setup
from setuptools.command.build_py import build_py


ROOT = Path(__file__).resolve().parent
SOURCE_PACKAGE = ROOT / "src" / "grpc_frame"
GENERATOR = SOURCE_PACKAGE / "util" / "build_proto.py"


class BuildPy(build_py):
    def run(self) -> None:
        # Copy the package first, then replace the generated modules in build_lib.
        # This avoids changing tracked source files during packaging.
        super().run()
        spec = importlib.util.spec_from_file_location("grpc_frame_proto_builder", str(GENERATOR))
        if spec is None or spec.loader is None:
            raise RuntimeError("Unable to load grpc_frame proto generator")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output = Path(self.build_lib) / "grpc_frame"
        output.mkdir(parents=True, exist_ok=True)
        for name in ("ctrl", "events"):
            module.build_proto(
                proto_name=name,
                proto_dir=str(SOURCE_PACKAGE),
                out_dir=str(output),
                frame_package="grpc_frame",
            )


setup(cmdclass={"build_py": BuildPy})
