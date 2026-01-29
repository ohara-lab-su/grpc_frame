#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

from concurrent import futures
from typing import Any, Optional

import grpc

from grpc_frame import adapter
from grpc_frame import ctrl_pb2
from grpc_frame import ctrl_pb2_grpc
from grpc_frame import dispatch_core


class ControlServicer(ctrl_pb2_grpc.ControlServicer):
    def __init__(
        self,
        *,
        ctrl_obj: Any,
    ) -> None:
        self._ctrl_obj: Any = ctrl_obj

    def Call(
        self,
        request: ctrl_pb2.DispatchRequest,
        context: grpc.ServicerContext,
    ) -> ctrl_pb2.DispatchResponse:
        resp: ctrl_pb2.DispatchResponse = ctrl_pb2.DispatchResponse()

        try:
            method_name: str = request.method
            fn = dispatch_core.resolve_ctrl_method(self._ctrl_obj, method_name)

            args = adapter.unpack_args(request.args)
            kwargs = adapter.unpack_kwargs(request.kwargs)

            result: Any = fn(*args, **kwargs)

            resp.ok = True
            resp.result = adapter.pack_result(result)
            resp.error = ""
            return resp

        except Exception as ex:
            resp.ok = False
            resp.result = b""
            resp.error = str(ex)
            return resp


class GrpcServer:
    def __init__(
        self,
        *,
        bind_ip: str,
        bind_port: int,
        ctrl_obj: Any,
        max_workers: int = 10,
    ) -> None:
        self._bind_ip: str = bind_ip
        self._bind_port: int = bind_port
        self._ctrl_obj: Any = ctrl_obj
        self._max_workers: int = max_workers

        self._server: Optional[grpc.Server] = None

    def start(self) -> None:
        executor = futures.ThreadPoolExecutor(max_workers=self._max_workers)
        server: grpc.Server = grpc.server(executor)

        servicer = ControlServicer(ctrl_obj=self._ctrl_obj)
        ctrl_pb2_grpc.add_ControlServicer_to_server(servicer, server)

        addr: str = f"{self._bind_ip}:{self._bind_port}"
        server.add_insecure_port(addr)

        server.start()
        self._server = server

    def wait_forever(self) -> None:
        if self._server is None:
            raise RuntimeError("server is not started")

        self._server.wait_for_termination()

    def stop(self, grace: float = 0.0) -> None:
        if self._server is None:
            return

        self._server.stop(grace)
        self._server = None
