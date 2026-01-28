#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, Optional, Type

import grpc

import adapter


class DynamicGrpcServer:
    """
    ctrl オブジェクトの public メソッドを走査し、
    proto の Service 定義に存在する RPC 名だけを自動でサーバへ登録する。

    - 通信は DispatchRequest(args, kwargs) のみ
    - server 側では常に ctrl_fn(*args, **kwargs) を再現する
    - client/ctrl の Python I/F に JSON を見せない
    """

    def __init__(
        self,
        *,
        ctrl: Any,
        pb2: Any,
        pb2_grpc: Any,
        service_name: str,
        server: grpc.Server,
    ) -> None:
        self._ctrl: Any = ctrl
        self._pb2: Any = pb2
        self._pb2_grpc: Any = pb2_grpc
        self._service_name: str = service_name
        self._server: grpc.Server = server

        self._register_dynamic_servicer()

    def _register_dynamic_servicer(self) -> None:
        service_desc: Any = self._pb2.DESCRIPTOR.services_by_name[self._service_name]
        base_servicer_cls: Any = getattr(self._pb2_grpc, f"{self._service_name}Servicer")
        add_fn: Any = getattr(self._pb2_grpc, f"add_{self._service_name}Servicer_to_server")

        pb2 = self._pb2
        ctrl_obj = self._ctrl

        class Servicer(base_servicer_cls):
            pass

        for m in service_desc.methods:
            rpc_name: str = m.name

            handler = self._make_handler(
                *,
                pb2=pb2,
                ctrl_obj=ctrl_obj,
                rpc_name=rpc_name,
            )
            setattr(Servicer, rpc_name, handler)

        add_fn(Servicer(), self._server)

    def _make_handler(
        self,
        *,
        pb2: Any,
        ctrl_obj: Any,
        rpc_name: str,
    ) -> Callable[[Any, Any, Any], Any]:
        def handler(self_: Any, request: Any, context: Any) -> Any:
            resp: Any = pb2.DispatchResponse()
            resp.ok = False
            resp.error = ""
            resp.result = b""

            if not hasattr(ctrl_obj, rpc_name):
                context.abort(grpc.StatusCode.UNIMPLEMENTED, f"ctrl has no method '{rpc_name}'")

            fn: Any = getattr(ctrl_obj, rpc_name)

            args_b: bytes = getattr(request, "args", b"")
            kwargs_b: bytes = getattr(request, "kwargs", b"")

            args_list: list[Any]
            kwargs_dict: Dict[str, Any]
            args_list, kwargs_dict = adapter.unpack_args_kwargs(args_b, kwargs_b)

            try:
                ret: Any = fn(*args_list, **kwargs_dict)
                resp.ok = True
                resp.result = adapter.dumps_json_bytes(ret).data
                return resp
            except TypeError as e:
                resp.ok = False
                resp.error = f"typeerror: {e}"
                return resp
            except Exception as e:
                resp.ok = False
                resp.error = f"exception: {e}"
                return resp

        handler.__name__ = rpc_name
        return handler