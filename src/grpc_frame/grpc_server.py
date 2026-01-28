#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import inspect
import traceback
from typing import Any, Callable, Type

import grpc

import grpc_frame.adapter
import grpc_frame.dispatch_core


def build_dynamic_servicer_class(
    *,
    pb2: Any,
    pb2_grpc: Any,
    service_name: str,
) -> Type[Any]:
    service_desc: Any = pb2.DESCRIPTOR.services_by_name[service_name]
    base_cls: Any = getattr(pb2_grpc, f"{service_name}Servicer")

    class Servicer(base_cls):
        def __init__(self, *, ctrl: Any) -> None:
            self._ctrl: Any = ctrl

    for m in service_desc.methods:
        rpc_name: str = m.name
        ctrl_name: str = dispatch_core.camel_to_snake(rpc_name)
        request_cls: Any = getattr(pb2, m.input_type.name)
        response_cls: Any = getattr(pb2, m.output_type.name)

        def make_handler(
            rpc_name_local: str,
            ctrl_name_local: str,
            request_cls_local: Any,
            response_cls_local: Any,
        ) -> Callable[..., Any]:
            def handler(self: Any, request: Any, context: Any) -> Any:
                resp: Any = response_cls_local()

                try:
                    fn: Any = getattr(self._ctrl, ctrl_name_local)

                    args_json: bytes = b""
                    kwargs_json: bytes = b""

                    if hasattr(request, "args_json"):
                        args_json = getattr(request, "args_json")
                    if hasattr(request, "kwargs_json"):
                        kwargs_json = getattr(request, "kwargs_json")

                    args_list = adapter.unpack_args(args_json)
                    kwargs_dict = adapter.unpack_kwargs(kwargs_json)

                    args = tuple(args_list)
                    kwargs = kwargs_dict

                    ret = fn(*args, **kwargs)

                    resp.ok = True
                    resp.result_json = adapter.pack_result(ret)
                    resp.error = ""
                    return resp

                except Exception as e:
                    tb: str = traceback.format_exc()
                    resp.ok = False
                    resp.result_json = b""
                    resp.error = f"{rpc_name_local} failed: {e}\n{tb}"
                    return resp

            handler.__name__ = rpc_name_local
            return handler

        setattr(
            Servicer,
            rpc_name,
            make_handler(
                rpc_name_local=rpc_name,
                ctrl_name_local=ctrl_name,
                request_cls_local=request_cls,
                response_cls_local=response_cls,
            ),
        )

    return Servicer


class GrpcServer:
    def __init__(
        self,
        *,
        pb2: Any,
        pb2_grpc: Any,
        service_name: str,
        ctrl: Any,
        server: grpc.Server,
    ) -> None:
        servicer_cls = build_dynamic_servicer_class(
            pb2=pb2,
            pb2_grpc=pb2_grpc,
            service_name=service_name,
        )
        servicer = servicer_cls(ctrl=ctrl)
        add_fn_name: str = f"add_{service_name}Servicer_to_server"

        add_fn: Any = getattr(pb2_grpc, add_fn_name)
        add_fn(servicer, server)
