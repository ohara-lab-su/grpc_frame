#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, Optional, Type

import grpc

import adapter
import dispatch_core


class GrpcClient:
    def __init__(
        self,
        *,
        server_ip: str,
        server_port: int,
        pb2: Any,
        pb2_grpc: Any,
        service_stub_class: Type[Any],
        ctrl_class: Type[Any],
        timeout_sec: Optional[float] = None,
    ) -> None:
        self._pb2: Any = pb2
        self._pb2_grpc: Any = pb2_grpc
        self._stub_class: Type[Any] = service_stub_class
        self._ctrl_class: Type[Any] = ctrl_class

        addr: str = f"{server_ip}:{server_port}"
        self._channel: grpc.Channel = grpc.insecure_channel(addr)
        self._stub: Any = self._stub_class(self._channel)

        self._timeout_sec: Optional[float] = timeout_sec

        self._bind_ctrl_methods()

    def _bind_ctrl_methods(self) -> None:
        for name, method in inspect.getmembers(self._ctrl_class, inspect.isfunction):
            if name.startswith("_"):
                continue

            rpc_name: str = dispatch_core.ctrl_method_to_rpc_name(name)

            has_rpc: bool = False
            if hasattr(self._stub, rpc_name):
                has_rpc = True

            if not has_rpc:
                continue

            rpc: Any = getattr(self._stub, rpc_name)
            sig: inspect.Signature = inspect.signature(method)

            dispatcher = self._make_dispatcher(
                method_name=name,
                sig=sig,
                rpc=rpc,
            )
            setattr(self, name, dispatcher)

    def _make_dispatcher(
        self,
        *,
        method_name: str,
        sig: inspect.Signature,
        rpc: Any,
    ) -> Callable[..., Any]:
        pb2 = self._pb2

        # RPC オブジェクトから input message クラスを取得する
        request_cls = rpc._method._input_class

        def _method(*args: Any, **kwargs: Any) -> Any:
            bound = sig.bind_partial(None, *args, **kwargs)

            args_json: bytes = adapter.pack_args(tuple(args))
            kwargs_json: bytes = adapter.pack_kwargs(kwargs)

            req: Any = request_cls()
            req.args_json = args_json
            req.kwargs_json = kwargs_json

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
