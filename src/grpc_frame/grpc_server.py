# grpc_frame/server.py
from __future__ import annotations

import inspect
import traceback
from typing import Any, Callable, Dict, List, Optional, Type

import grpc_frame.dispatch_core as core
import grpc_frame.util_server as server_util

from x_logger import XLogger


def build_dynamic_servicer_class(
    servicer_base_cls: Type[Any],
    ctrl: Any,
    logger: Optional[XLogger] = None,
) -> Type[Any]:
    logger_obj: XLogger = logger or XLogger()

    base_attrs: Dict[str, Any] = dict(servicer_base_cls.__dict__)

    rpc_name_list: List[str] = []
    for name, member in base_attrs.items():
        if name.startswith("_") is True:
            continue
        if callable(member) is False:
            continue
        rpc_name_list.append(name)

    logger_obj.info(f"[GrpcServer] found rpc methods = {rpc_name_list}")

    def _make_handler(rpc_name: str) -> Callable[..., Any]:
        rpc_method = getattr(servicer_base_cls, rpc_name, None)

        response_cls: Optional[Type[Any]] = None
        if rpc_method is not None:
            ann: Any = getattr(rpc_method, "__annotations__", None)
            if ann is not None:
                response_cls = ann.get("return", None)

        def _handler(self: Any, request: Any, context: Any) -> Any:
            method_name: str = core.camel_to_snake(rpc_name)
            logger_obj.info(f"[GrpcServer] CALL {rpc_name} -> ctrl.{method_name}")

            if hasattr(ctrl, method_name) is False:
                logger_obj.error(f"[GrpcServer] ctrl has no method: {method_name}")
                if response_cls is None:
                    return None
                resp0: Any = response_cls()
                if hasattr(resp0, "ok") is True:
                    setattr(resp0, "ok", False)
                return resp0

            ctrl_fn: Any = getattr(ctrl, method_name)

            try:
                plan: server_util.CtrlCallPlan = server_util.build_call_plan(
                    ctrl_fn, request
                )
                logger_obj.info(f"[GrpcServer] plan.args={plan.args}")
                logger_obj.info(f"[GrpcServer] plan.kwargs={plan.kwargs}")

                ret = ctrl_fn(*plan.args, **plan.kwargs)

                if response_cls is None:
                    return ret

                resp: Any = response_cls()
                server_util.fill_response_message(resp, ret)
                return resp

            except Exception:
                tb: str = traceback.format_exc()
                logger_obj.error(f"[GrpcServer] exception in {rpc_name}:\n{tb}")

                if response_cls is None:
                    return None

                resp2: Any = response_cls()
                if hasattr(resp2, "ok") is True:
                    setattr(resp2, "ok", False)
                return resp2

        _handler.__name__ = rpc_name
        return _handler

    dynamic_attrs: Dict[str, Any] = {}

    def _init(self: Any, injected_ctrl: Any, injected_logger: XLogger) -> None:
        self._ctrl = injected_ctrl
        self._logger = injected_logger

    dynamic_attrs["__init__"] = _init

    for rpc_name in rpc_name_list:
        dynamic_attrs[rpc_name] = _make_handler(rpc_name)

    dynamic_name: str = f"Dynamic{servicer_base_cls.__name__}"
    dynamic_cls: Type[Any] = type(dynamic_name, (servicer_base_cls,), dynamic_attrs)

    logger_obj.info(f"[GrpcServer] dynamic servicer class created: {dynamic_cls}")
    return dynamic_cls
