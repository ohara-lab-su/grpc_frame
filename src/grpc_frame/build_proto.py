#!/usr/bin/env python3
"""
joypad.proto を gRPC (Python) 用コードにビルドするスクリプト
Kengo NAKADA
kengo.nakada@mat.shimane-u.ac.jp
kengo.nakada@gmail.com
"""

from typing import Any, Dict, List, Optional, Union, Tuple, Callable, Sequence
import os
import sys
from grpc_tools import protoc

#!/usr/bin/env python3
from typing import Optional
import os
from grpc_tools import protoc


def build_proto(
    *,
    proto_name: str,
    proto_dir: Optional[str] = None,
    out_dir: Optional[str] = None,
    frame_package: str = "grpc_frame",
) -> None:
    """
    フレーム内 proto を gRPC Python 用にビルドする

    proto_name:
        "ctrl", "events", "joypad" など（拡張子なし）
    proto_dir:
        proto のあるディレクトリ（Noneならこのファイルの場所）
    out_dir:
        出力先（Noneなら proto_dir）
    frame_package:
        生成物が属する Python パッケージ名（通常 "grpc_frame"）
    """
    here = os.path.dirname(os.path.abspath(__file__))

    if proto_dir is None:
        proto_dir = here
    if out_dir is None:
        out_dir = proto_dir

    proto_file = os.path.join(proto_dir, f"{proto_name}.proto")
    if not os.path.exists(proto_file):
        raise FileNotFoundError(proto_file)

    cmd = [
        "grpc_tools.protoc",
        f"-I{proto_dir}",
        f"--python_out={out_dir}",
        f"--grpc_python_out={out_dir}",
        proto_file,
    ]

    result = protoc.main(cmd)
    if result != 0:
        raise RuntimeError(f"protoc failed: {result}")

    # --- *_pb2_grpc.py の import をフル修飾に直す ---
    grpc_py = os.path.join(out_dir, f"{proto_name}_pb2_grpc.py")
    if not os.path.exists(grpc_py):
        raise FileNotFoundError(grpc_py)

    with open(grpc_py, "r", encoding="utf-8") as f:
        text = f.read()

    old = f"import {proto_name}_pb2 as {proto_name}__pb2"
    new = f"from {frame_package} import {proto_name}_pb2 as {proto_name}__pb2"

    if old not in text:
        raise RuntimeError(f"unexpected import line in {grpc_py}")

    text = text.replace(old, new)

    with open(grpc_py, "w", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    build_proto(
        proto_name="ctrl",
    )


# def main():
#     here = os.path.dirname(os.path.abspath(__file__))
#     # proto_file = os.path.join(here, "joypad.proto")
#     proto_file = os.path.join(here, "ctrl.proto")
#
#     # 出力先は同ディレクトリ
#     out_dir = here
#
#     cmd = [
#         "grpc_tools.protoc",
#         f"-I{here}",
#         f"--python_out={out_dir}",
#         f"--grpc_python_out={out_dir}",
#         proto_file,
#     ]
#
#     print("Running protoc:")
#     print(" ".join(cmd))
#
#     # protoc を python 経由で呼ぶ
#     result = protoc.main(cmd)
#
#     if result != 0:
#         print(f"protoc failed with code {result}")
#         sys.exit(result)
#     else:
#         # 生成後に joypad_pb2_grpc.py の import を絶対インポートに書き換える
#         grpc_path = os.path.join(out_dir, "joypad_pb2_grpc.py")
#
#         try:
#             with open(grpc_path, "r", encoding="utf-8") as f:
#                 text = f.read()
#         except FileNotFoundError:
#             print(f"Error: {grpc_path} が見つかりません")
#             sys.exit(1)
#
#         # protoc が生成する標準の行を絶対インポートに置き換え
#         old = "import joypad_pb2 as joypad__pb2"
#         new = "from cobotta2.server_grpc import joypad_pb2 as joypad__pb2"
#
#         if old in text:
#             text = text.replace(old, new)
#             with open(grpc_path, "w", encoding="utf-8") as f:
#                 f.write(text)
#         else:
#             # 想定と違う生成結果になっている場合のデバッグ用メッセージ
#             print(f"Warning: '{old}' が {grpc_path} 内に見つかりませんでした")
#
#         print("protoc build complete:")
#         print("  joypad_pb2.py")
#         print("  joypad_pb2_grpc.py")
#
#
# if __name__ == "__main__":
#     main()
#
