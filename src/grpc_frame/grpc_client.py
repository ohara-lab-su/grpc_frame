from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, Optional, Type

import grpc
from google.protobuf import empty_pb2

import grpc_frame.core as core
from x_logger import XLogger


class GrpcClient:
    _ctrl_class: Type[Any]
    _stub_class: Type[Any]
    _client_log_title: str

    def __init__(
        self,
        server_ip: str,
        server_port: int,
        logger: Optional[XLogger] = None,
    ) -> None:
        self._logger = logger or XLogger()
        addr = f"{server_ip}:{server_port}"
        self._channel = grpc.insecure_channel(addr)
        self._stub = self._stub_class(self._channel)

        self._bind_ctrl_methods()

    def is_connected(self, timeout: float = 0.5) -> bool:
        try:
            grpc.channel_ready_future(self._channel).result(timeout=timeout)
            return True
        except Exception:
            return False

    def _bind_ctrl_methods(self) -> None:
        for name, method in inspect.getmembers(self._ctrl_class, inspect.isfunction):
            if name.startswith("_"):
                continue

            rpc_name = core.ctrl_method_to_rpc_name(name)
            if not hasattr(self._stub, rpc_name):
                continue

            rpc = getattr(self._stub, rpc_name)
            sig = inspect.signature(method)

            def _make_dispatcher(rpc, sig, name):
                def _method(*args, **kwargs):
                    bound = sig.bind_partial(None, *args, **kwargs)
                    req_kwargs = {
                        k: v for k, v in bound.arguments.items() if k != "self"
                    }
                    request = core.build_request_message(
                        core._resolve_request_class_from_rpc(
                            rpc, self._stub_class, self._logger
                        ),
                        req_kwargs,
                    )
                    resp = rpc(request)
                    return core.unwrap_response(resp)

                _method.__name__ = name
                _method.__signature__ = sig
                return _method

            setattr(self, name, _make_dispatcher(rpc, sig, name))
