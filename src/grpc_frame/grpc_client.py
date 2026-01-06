#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gRPC client implementation (framework layer)

責務:
- stub を introspection
- ctrl と同じ形の Python API を生成
"""

import inspect
import grpc
from typing import Any, Callable, Optional

from .dispatch_core import to_rpc_name, protobuf_to_python


class GrpcClient:
    def __init__(
        self,
        *,
        stub_class: Any,
        ctrl_class: Any,
        channel: grpc.Channel,
        logger: Optional[Any] = None,
    ):
        self._stub = stub_class(channel)
        self._logger = logger
        self._bind(ctrl_class)

    def _bind(self, ctrl_class: Any) -> None:
        for name, fn in inspect.getmembers(ctrl_class, inspect.isfunction):
            if name.startswith("_"):
                continue

            rpc_name = to_rpc_name(name)
            if hasattr(self._stub, rpc_name) is False:
                continue

            rpc = getattr(self._stub, rpc_name)
            sig = inspect.signature(fn)

            def make_method(method_name, rpc_call, sig_local):
                def method(*args, **kwargs):
                    bound = sig_local.bind_partial(None, *args, **kwargs)
                    bound.apply_defaults()
                    req_kwargs = {
                        k: v for k, v in bound.arguments.items() if k != "self"
                    }
                    resp = rpc_call(**req_kwargs)
                    return protobuf_to_python(resp)

                method.__name__ = method_name
                method.__signature__ = sig_local
                return method

            setattr(self, name, make_method(name, rpc, sig))