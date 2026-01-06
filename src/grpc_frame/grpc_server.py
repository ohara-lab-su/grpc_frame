#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import traceback
from typing import Any, Type
import grpc

import grpc_dispatch_core as core
from x_logger import XLogger


def build_servicer(
    *,
    pb2: Any,
    pb2_grpc: Any,
    service_name: str,
) -> Type[Any]:

    service_desc = pb2.DESCRIPTOR.services_by_name[service_name]
    base_cls = getattr(pb2_grpc, f"{service_name}Servicer")

    class Servicer(base_cls):
        def __init__(self, *, ctrl: Any, logger: XLogger):
            self._ctrl = ctrl
            self._logger = logger

    for m in service_desc.methods:
        rpc_name = m.name
        ctrl_name = core.camel_to_snake(rpc_name)
        response_cls = getattr(pb2, m.output_type.name)

        def make_handler(rpc_name_local, ctrl_name_local, response_cls_local):
            def handler(self, request, context):
                try:
                    fn = getattr(self._ctrl, ctrl_name_local)
                    plan = core.build_call_plan(fn, request)
                    ret = fn(*plan.args, **plan.kwargs)
                except AttributeError:
                    context.abort(
                        grpc.StatusCode.UNIMPLEMENTED,
                        f"ctrl has no method '{ctrl_name_local}'",
                    )
                except Exception:
                    self._logger.error(traceback.format_exc())
                    context.abort(
                        grpc.StatusCode.INTERNAL,
                        f"{rpc_name_local} failed",
                    )

                resp = response_cls_local()
                return core.fill_response_message(resp, ret)

            return handler

        setattr(Servicer, rpc_name, make_handler(rpc_name, ctrl_name, response_cls))

    return Servicer