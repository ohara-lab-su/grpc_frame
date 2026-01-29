#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, Optional, Type

import grpc

from grpc_frame.adapter import *
from grpc_frame.dispatch_core import *


class GrpcClient:
    def __init__(
        self,
        *,
        server_ip: str,
        server_port: int,
        ctrl_class: Type[Any],
        timeout_sec: Optional[float] = None,
        logger: Optional[Any] = None,
    ) -> None:
        """"""
        self._ctrl_class: Type[Any] = ctrl_class

        addr: str = f"{server_ip}:{server_port}"
        self._channel: grpc.Channel = grpc.insecure_channel(addr)
        self._timeout_sec: Optional[float] = timeout_sec

        self._bind_ctrl_methods()

    def _bind_ctrl_methods(self) -> None:
        for name, method in inspect.getmembers(self._ctrl_class, inspect.isfunction):
            if name.startswith("_"):
                continue

            rpc_name: str = dispatch_core.ctrl_method_to_rpc_name(name)

            sig: inspect.Signature = inspect.signature(method)

            dispatcher = self._make_dispatcher(
                method_name=name,
                sig=sig,
            )
            setattr(self, name, dispatcher)

    def _make_dispatcher(
        self,
        *,
        method_name: str,
        sig: inspect.Signature,
    ) -> Callable[..., Any]:

        rpc_full_name: str = f"/ctrl.JoyPadCtrl/{method_name}"

        rpc = self._channel.unary_unary(
            rpc_full_name,
            request_serializer=lambda x: x.SerializeToString(),
            response_deserializer=lambda x: DispatchResponse.FromString(x),
        )

        def _method(*args: Any, **kwargs: Any) -> Any:
            bound = sig.bind_partial(None, *args, **kwargs)

            args_json: bytes = adapter.pack_args(tuple(args))
            kwargs_json: bytes = adapter.pack_kwargs(kwargs)

            req = DispatchRequest(
                args=args_json,
                kwargs=kwargs_json,
            )

            resp: Any
            if self._timeout_sec is None:
                resp = rpc(req)
            else:
                resp = rpc(req, timeout=self._timeout_sec)

            ok: bool = False
            if hasattr(resp, "ok"):
                ok = bool(getattr(resp, "ok"))

            if ok:
                result_json: bytes = b""
                if hasattr(resp, "result_json"):
                    result_json = getattr(resp, "result_json")
                return adapter.unpack_result(result_json)

            err: str = ""
            if hasattr(resp, "error"):
                err = str(getattr(resp, "error"))
            raise RuntimeError(err)

        _method.__name__ = method_name
        _method.__signature__ = sig
        return _method
