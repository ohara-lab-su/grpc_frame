#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

import grpc

from grpc_frame.adapter import *
from grpc_frame.dispatch_core import *
from grpc_frame.ctrl_pb2 import ctrl_pb2
from grpc_frame.ctrl_pb2_grpc import ctrl_pb2_grpc


class _ControlServicer(ctrl_pb2_grpc.ControlServicer):
    def __init__(self, ctrl_obj: Any, logger: Optional[Any] = None) -> None:
        self._ctrl_obj: Any = ctrl_obj
        self._logger: Optional[Any] = logger

    def Describe(self, request: ctrl_pb2.Empty, context: Any) -> ctrl_pb2.MethodTable:
        infos = dispatch_core.list_public_methods(self._ctrl_obj)

        table = ctrl_pb2.MethodTable()
        for info in infos:
            mi = table.methods.add()
            mi.name = info.name
            mi.signature = info.signature
        return table

    def Call(
        self, request: ctrl_pb2.DispatchRequest, context: Any
    ) -> ctrl_pb2.DispatchResponse:
        method_name: str = str(request.method)

        try:
            target = getattr(self._ctrl_obj, method_name)
        except Exception as e:
            return ctrl_pb2.DispatchResponse(ok=False, result=b"", error=str(e))

        try:
            args = adapter.unpack_args(request.args)
            kwargs = adapter.unpack_kwargs(request.kwargs)

            result = target(*args, **kwargs)
            result_bin: bytes = adapter.pack_result(result)
            return ctrl_pb2.DispatchResponse(ok=True, result=result_bin, error="")
        except Exception as e:
            return ctrl_pb2.DispatchResponse(ok=False, result=b"", error=str(e))


class GrpcServer:
    def __init__(
        self,
        ctrl_obj: Any,
        bind_ip: str,
        bind_port: int,
        logger: Optional[Any] = None,
        max_workers: int = 10,
    ) -> None:
        self._ctrl_obj: Any = ctrl_obj
        self._bind_ip: str = bind_ip
        self._bind_port: int = bind_port
        self._logger: Optional[Any] = logger

        self._grpc_server = grpc.server(ThreadPoolExecutor(max_workers=max_workers))
        ctrl_pb2_grpc.add_ControlServicer_to_server(
            _ControlServicer(ctrl_obj=self._ctrl_obj, logger=self._logger),
            self._grpc_server,
        )

        self._addr: str = f"{self._bind_ip}:{self._bind_port}"
        self._grpc_server.add_insecure_port(self._addr)

    def start(self) -> None:
        self._grpc_server.start()

    def wait(self) -> None:
        self._grpc_server.wait_for_termination()

    def stop(self, grace_sec: float = 0.0) -> None:
        self._grpc_server.stop(grace_sec)
