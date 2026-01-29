#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Callable, Optional

import grpc

from grpc_frame import adapter
from grpc_frame import ctrl_pb2


class GrpcClient:
    def __init__(
        self,
        *,
        server_ip: str,
        server_port: int,
        timeout_sec: Optional[float] = None,
    ) -> None:
        addr: str = f"{server_ip}:{server_port}"

        self._timeout_sec: Optional[float] = timeout_sec
        self._channel: grpc.Channel = grpc.insecure_channel(addr)

        method_path: str = "/ctrl.Control/Call"

        self._call_rpc = self._channel.unary_unary(
            method_path,
            request_serializer=ctrl_pb2.DispatchRequest.SerializeToString,
            response_deserializer=ctrl_pb2.DispatchResponse.FromString,
        )

    def __getattr__(self, method_name: str) -> Callable[..., Any]:
        def _method(*args: Any, **kwargs: Any) -> Any:
            args_json: bytes = adapter.pack_args(tuple(args))
            kwargs_json: bytes = adapter.pack_kwargs(kwargs)

            req: ctrl_pb2.DispatchRequest = ctrl_pb2.DispatchRequest()
            req.method = method_name
            req.args = args_json
            req.kwargs = kwargs_json

            if self._timeout_sec is None:
                resp: ctrl_pb2.DispatchResponse = self._call_rpc(req)
            else:
                resp = self._call_rpc(req, timeout=self._timeout_sec)

            if resp.ok:
                return adapter.unpack_result(resp.result)

            raise RuntimeError(resp.error)

        _method.__name__ = method_name
        return _method
