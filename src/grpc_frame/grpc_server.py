from __future__ import annotations

import inspect
import traceback
from typing import Any, Callable, Dict, List, Optional, Type

import grpc_frame.core as core
from x_logger import XLogger


def build_dynamic_servicer_class(
    servicer_base_cls: Type[Any],
    ctrl: Any,
    logger: Optional[XLogger] = None,
) -> Type[Any]:
    logger_obj = logger or XLogger()

    rpc_names: List[str] = [
        name
        for name, member in servicer_base_cls.__dict__.items()
        if callable(member) and not name.startswith("_")
    ]

    def _make_handler(rpc_name: str) -> Callable[..., Any]:
        rpc_method = getattr(servicer_base_cls, rpc_name, None)

        response_cls = None
        if rpc_method is not None:
            ann = getattr(rpc_method, "__annotations__", None)
            if ann:
                response_cls = ann.get("return", None)

        def _handler(self: Any, request: Any, context: Any) -> Any:
            method_name = core.camel_to_snake(rpc_name)

            if not hasattr(ctrl, method_name):
                if response_cls is None:
                    return None
                resp = response_cls()
                if hasattr(resp, "ok"):
                    resp.ok = False
                return resp

            try:
                ctrl_fn = getattr(ctrl, method_name)
                plan = core.build_call_plan(ctrl_fn, request)
                ret = ctrl_fn(*plan.args, **plan.kwargs)

                if response_cls is None:
                    return ret

                resp = response_cls()
                core.fill_response_message(resp, ret)
                return resp

            except Exception:
                logger_obj.error(traceback.format_exc())
                if response_cls is None:
                    return None
                resp = response_cls()
                if hasattr(resp, "ok"):
                    resp.ok = False
                return resp

        _handler.__name__ = rpc_name
        return _handler

    attrs: Dict[str, Any] = {}

    def _init(self: Any, injected_ctrl: Any, injected_logger: XLogger) -> None:
        self._ctrl = injected_ctrl
        self._logger = injected_logger

    attrs["__init__"] = _init

    for rpc in rpc_names:
        attrs[rpc] = _make_handler(rpc)

    return type(f"Dynamic{servicer_base_cls.__name__}", (servicer_base_cls,), attrs)
