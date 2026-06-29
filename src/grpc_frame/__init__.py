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

# --- public API (client) ---
from grpc_frame.grpc_client import AsyncGrpcClient
from grpc_frame.grpc_client import SyncGrpcClient
from grpc_frame.grpc_client import GrpcClient


# --- public API (DeviceProxy) ---
from grpc_frame.device_proxy import DeviceProxyEntry
from grpc_frame.device_proxy import register_device_proxy
from grpc_frame.device_proxy import unregister_device_proxy
from grpc_frame.device_proxy import get_device_proxy_entry
from grpc_frame.device_proxy import list_device_proxies
from grpc_frame.device_proxy import DeviceProxy
from grpc_frame.device_proxy import create_device_proxy

# --- public API for COM (server) ---
from grpc_frame.grpc_com import ComExecutionRunner
from grpc_frame.grpc_com import ThreadSafeCtrlProxy

# --- public API (server) ---
from grpc_frame.grpc_server import _ControlServicer
from grpc_frame.dispatch_core import *
from grpc_frame.adapter import *

# --- pyi generation ---
from grpc_frame.make_pyi import generate_client_pyi
