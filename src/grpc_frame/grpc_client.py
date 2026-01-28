#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import inspect
from typing import Any, Callable, Optional, Type

import grpc

import adapter


class GrpcClient:
    """
    ctrl_class の public メソッド一覧を走査し、同名 RPC が proto に存在するものを
    client 側に動的に生やす。

    - 呼び出しは client.method(*args, **kwargs) のまま
    - 送るのは JSON bytes (args/kwargs)
    - 返り値は JSON bytes を Python 値へ戻す（型は問わない）
    """

    def __init__(
        self,
        *,
        server_ip: str,
        server_port: int,
        pb2: Any,
        pb2_grpc: Any,
        service_name: str,
        ctrl_class: Type[Any],
        timeout_sec: Optional[float] = None,
    ) -> None:
        self._server_ip: str = server_ip
        self._server_port: int = server_port
        self._pb2: Any = pb2
        self._pb2_grpc: Any = pb2_grpc
        self._service_name: str = service_name
        self._ctrl_class: Type[Any] = ctrl_class
        self._timeout_sec: Optional[float] = timeout_sec

        addr: str = f"{server_ip}:{server_port}"
        self._channel: grpc.Channel = grpc.insecure_channel(addr)
        self._stub: Any = getattr(pb2_grpc, f"{service_name}Stub")(self._channel)

        self._bind_methods()

    def _bind_methods(self) -> None:
        service_desc: Any = self._pb2.DESCRIPTOR.services_by_name[self._service_name]
        rpc_names: set[str] = set()
        for m in service_desc.methods:
            rpc_names.add(m.name)

        for name, method in inspect.getmembers(self._ctrl_class, inspect.isfunction):
            if name.startswith("_"):
                continue
            if name not in rpc_names:
                continue

            rpc_callable: Any = getattr(self._stub, name)
            sig: inspect.Signature = inspect.signature(method)

            dispatcher = self._make_dispatcher(
                *,
                method_name=name,
                sig=sig,
                rpc_callable=rpc_callable,
            )
            setattr(self, name, dispatcher)

    def _make_dispatcher(
        self,
        *,
        method_name: str,
        sig: inspect.Signature,
        rpc_callable: Any,
    ) -> Callable[..., Any]:
        pb2 = self._pb2
        timeout = self._timeout_sec

        def _method(*args: Any, **kwargs: Any) -> Any:
            # 文法レベル（keyword-only 等）の整合チェック
            try:
                bound = sig.bind(None, *args, **kwargs)
                _ = bound
            except TypeError as e:
                return False

            args_b: bytes
            kwargs_b: bytes
            args_b, kwargs_b = adapter.pack_args_kwargs(*args, **kwargs)

            req: Any = pb2.DispatchRequest()
            req.args = args_b
            req.kwargs = kwargs_b

            resp: Any
            if timeout is None:
                resp = rpc_callable(req)
            else:
                resp = rpc_callable(req, timeout=timeout)

            ok: bool = bool(getattr(resp, "ok", False))
            if ok:
                result_b: bytes = getattr(resp, "result", b"")
                return adapter.loads_json_bytes(result_b)

            return False

        _method.__name__ = method_name
        _method.__signature__ = sig
        return _method