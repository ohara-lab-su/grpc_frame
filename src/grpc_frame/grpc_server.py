#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gRPC server implementation (framework layer)

責務:
- proto service 定義から Servicer を構築
- request を dispatch_core に渡す
- ctrl を呼び、response を返す
"""

import grpc
import traceback
from typing import Any, Type

from .dispatch_core import (
    camel_to_snake,
    build_call_plan,
    fill_response_message,
)


def build_servicer(
    *,
    pb2: Any,
    pb2_grpc: Any,
    service_name: str,
) -> Type[Any]:

    service_desc = pb2.DESCRIPTOR.services_by_name[service_name]
    base = getattr(pb2_grpc, f"{service_name}Servicer")

    class Servicer(base):
        def __init__(self, ctrl: Any, logger: Any):
            self._ctrl = ctrl
            self._logger = logger

    for method in service_desc.methods:
        rpc_name = method.name
        ctrl_name = camel_to_snake(rpc_name)
        response_cls = getattr(pb2, method.output_type.name)

        def make_handler(rpc_name_local, ctrl_name_local, response_cls_local):
            def handler(self, request, context):
                try:
                    fn = getattr(self._ctrl, ctrl_name_local)
                    plan = build_call_plan(fn, request)
                    ret = fn(*plan.args, **plan.kwargs)
                except AttributeError:
                    context.abort(
                        grpc.StatusCode.UNIMPLEMENTED,
                        f"ctrl has no method '{ctrl_name_local}'",
                    )
                except Exception as e:
                    self._logger.error(traceback.format_exc())
                    context.abort(
                        grpc.StatusCode.INTERNAL,
                        f"{rpc_name_local} failed: {e}",
                    )

                resp = response_cls_local()
                return fill_response_message(resp, ret)

            return handler

        setattr(
            Servicer,
            rpc_name,
            make_handler(rpc_name, ctrl_name, response_cls),
        )

    return Servicer