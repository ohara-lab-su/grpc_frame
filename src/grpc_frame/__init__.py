from __future__ import annotations

import sys

# --- proto stub alias (重要) ---
from grpc_frame import ctrl_pb2 as _ctrl_pb2

sys.modules["ctrl_pb2"] = _ctrl_pb2

# --- public API ---
from grpc_frame.grpc_client import GrpcClient
from grpc_frame.grpc_server import build_dynamic_servicer_class
from grpc_frame.dispatch_core import *
from grpc_frame.adapter import *
