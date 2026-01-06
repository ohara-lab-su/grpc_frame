#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import inspect
import grpc
from typing import Any, Callable, Optional, Type

import grpc_dispatch_core as core
from x_logger import XLogger


class GrpcClient:
    _ctrl_class: Type[Any]
    _stub_class: Type[Any]
    _client_log_title: str

    def __init__(
        self,
        *,
        server_ip: str,
        server_port: int,
        logger: Optional[XLogger] = None,
    ) -> None:
        self._logger = logger or XLogger()
        addr = f"{server_ip}:{server_port}"
        self._channel = grpc.insecure_channel(addr)
        self._stub = self._stub_class(self._channel)

        self._logger.info(f"== Create {self._client_log_title}")
        self._logger.info(f" gRPC server = {addr}")

        self._bind_ctrl_methods()

    def _bind_ctrl_methods(self) -> None:
        for name, fn in inspect.getmembers(self._ctrl_class, inspect.isfunction):
            if name.startswith("_"):
                continue

            rpc_name = core.to_rpc_name(name)
            if not hasattr(self._stub, rpc_name):
                continue

            rpc = getattr(self._stub, rpc_name)
            sig = inspect.signature(fn)

            def make_method(method_name, sig_local, rpc_call):
                def method(*args, **kwargs):
                    bound = sig_local.bind_partial(None, *args, **kwargs)
                    bound.apply_defaults()
                    req_kwargs = {k: v for k, v in bound.arguments.items() if k != "self"}
                    request_cls = rpc_call._request_serializer.__self__.__class__
                    request = core.build_request_message(request_cls, req_kwargs)
                    resp = rpc_call(request)
                    return core.unwrap_response(resp)

                method.__name__ = method_name
                method.__signature__ = sig_local
                return method

            setattr(self, name, make_method(name, sig, rpc))

    def is_connected(self, timeout: float = 0.5) -> bool:
        try:
            grpc.channel_ready_future(self._channel).result(timeout=timeout)
            return True
        except Exception:
            return False