#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

import grpc

import grpc_frame.adapter as adapter
import grpc_frame.dispatch_core as dispatch_core

import grpc_frame.ctrl_pb2 as ctrl_pb2
import grpc_frame.ctrl_pb2_grpc as ctrl_pb2_grpc


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
