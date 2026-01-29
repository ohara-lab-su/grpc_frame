#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

import grpc

from grpc_frame.adapter import *
import grpc_frame.ctrl_pb2 as ctrl_pb2


class GrpcClient:
    def __init__(
        self,
        server_ip: str,
        server_port: int,
        logger: Optional[Any] = None,
        log_level: str = "INFO",
        timeout_sec: Optional[float] = None,
    ) -> None:
        self._logger: Optional[Any] = logger
        self._timeout_sec: Optional[float] = timeout_sec

        addr: str = f"{server_ip}:{server_port}"
        self._channel: grpc.Channel = grpc.insecure_channel(addr)

        self._rpc_describe = self._channel.unary_unary(
            "/ctrl.Control/Describe",
            request_serializer=ctrl_pb2.Empty.SerializeToString,
            response_deserializer=ctrl_pb2.MethodTable.FromString,
        )
        self._rpc_call = self._channel.unary_unary(
            "/ctrl.Control/Call",
            request_serializer=ctrl_pb2.DispatchRequest.SerializeToString,
            response_deserializer=ctrl_pb2.DispatchResponse.FromString,
        )

        self._method_table: Dict[str, str] = {}
        self._bind_remote_methods()

    def is_connected(self) -> bool:
        try:
            _ = self._rpc_describe(ctrl_pb2.Empty(), timeout=self._timeout_sec)
            return True
        except Exception:
            return False

    def _bind_remote_methods(self) -> None:
        table = self._rpc_describe(ctrl_pb2.Empty(), timeout=self._timeout_sec)

        for m in table.methods:
            name: str = str(m.name)
            sig: str = str(m.signature)
            self._method_table[name] = sig

            dispatcher = self._make_dispatcher(method_name=name)
            setattr(self, name, dispatcher)

    def _make_dispatcher(self, *, method_name: str) -> Callable[..., Any]:
        def _method(*args: Any, **kwargs: Any) -> Any:
            args_bin: bytes = adapter.pack_args(tuple(args))
            kwargs_bin: bytes = adapter.pack_kwargs(kwargs)

            req = ctrl_pb2.DispatchRequest(
                method=method_name,
                args=args_bin,
                kwargs=kwargs_bin,
            )

            resp = self._rpc_call(req, timeout=self._timeout_sec)

            ok: bool = bool(resp.ok)
            if ok:
                return adapter.unpack_result(resp.result)

            err: str = str(resp.error)
            raise RuntimeError(err)

        _method.__name__ = method_name
        return _method

    def close(self) -> None:
        try:
            self._channel.close()
        except Exception:
            pass
