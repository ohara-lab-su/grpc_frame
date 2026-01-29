from __future__ import annotations

import sys

# -- gRPC スタブ
from grpc_frame import ctrl_pb2 as _ctrl_pb2

# ctrl_pb2 を トップレベル名として解決できるように
sys.modules["ctrl_pb2"] = _ctrl_pb2

# --- public API ---
from grpc_frame.grpc_client import GrpcClient
from grpc_frame.grpc_server import _ControlServicer
from grpc_frame.dispatch_core import *
from grpc_frame.adapter import *
