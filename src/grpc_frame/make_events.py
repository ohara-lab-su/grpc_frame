#!/usr/bin/env python3
"""
joypad.proto を gRPC (Python) 用コードにビルドするスクリプト
Kengo NAKADA
kengo.nakada@mat.shimane-u.ac.jp
kengo.nakada@gmail.com
"""

# from build_proto import build_proto as build_proto
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


if __name__ == "__main__":
    # from .build_proto import build_proto
    from grpc_frame.build_proto import build_proto

    build_proto(
        proto_name="events",
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
