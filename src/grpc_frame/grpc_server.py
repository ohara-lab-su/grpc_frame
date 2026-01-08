# grpc_frame/grpc_server.py
from __future__ import annotations

import traceback
from typing import Any, Type

import grpc


import grpc_frame.dispatch_core as core
from x_logger import XLogger


def build_dynamic_servicer_class(
    *,
    pb2: Any,
    pb2_grpc: Any,
    service_name: str,
) -> Type[Any]:
    service_desc: Any = pb2.DESCRIPTOR.services_by_name[service_name]
    base_cls: Any = getattr(pb2_grpc, f"{service_name}Servicer")

    class Servicer(base_cls):
        def __init__(self, *, ctrl: Any, logger: XLogger) -> None:
            self._ctrl: Any = ctrl
            self._logger: XLogger = logger

    for m in service_desc.methods:
        rpc_name: str = m.name
        ctrl_name: str = core.camel_to_snake(rpc_name)
        response_cls: Any = getattr(pb2, m.output_type.name)

        def make_handler(
            rpc_name_local: str,
            ctrl_name_local: str,
            response_cls_local: Any,
        ):
            def handler(self: Any, request: Any, context: Any) -> Any:
                try:
                    fn: Any = getattr(self._ctrl, ctrl_name_local)
                    plan = core.build_call_plan(fn, request)

                    if len(plan.kwargs) == 0:
                        ret = fn(*plan.args)
                    else:
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

                resp: Any = response_cls_local()
                return core.fill_response_message(resp, ret)

            return handler

        setattr(
            Servicer,
            rpc_name,
            make_handler(rpc_name, ctrl_name, response_cls),
        )

    return Servicer