from __future__ import annotations

import sys

# --- ctrl gRPC スタブ
from grpc_frame import ctrl_pb2 as _ctrl_pb2
from grpc_frame import ctrl_pb2_grpc as _ctrl_pb2_grpc

# ctrl_pb2 を トップレベル名として解決できるように
sys.modules["ctrl_pb2"] = _ctrl_pb2
sys.modules["ctrl_pb2_grpc"] = _ctrl_pb2_grpc

# --- events ---
from grpc_frame import events_pb2 as _events_pb2
from grpc_frame import events_pb2_grpc as _events_pb2_grpc

sys.modules["events_pb2"] = _events_pb2
sys.modules["events_pb2_grpc"] = _events_pb2_grpc

# --- public API ---
from grpc_frame.grpc_client import GrpcClient
from grpc_frame.grpc_server import _ControlServicer
from grpc_frame.dispatch_core import *
from grpc_frame.adapter import *

# --- public API ---
from grpc_frame.grpc_client import GrpcClient
from grpc_frame.grpc_server import _ControlServicer
from grpc_frame.dispatch_core import *
from grpc_frame.adapter import *
