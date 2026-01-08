# grpc_frame/grpc_server.py
from __future__ import annotations

import traceback
from typing import Any, Type

import grpc


import grpc_frame.dispatch_core as core
from x_logger import XLogger


@dataclass(frozen=True)
class CtrlCallPlan:
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]


def request_to_kwargs(
    req: Any,
) -> Dict[str, Any]:
    """

    Args:
        req:

    Returns:

    """
    kwargs: Dict[str, Any] = {}

    for f in req.DESCRIPTOR.fields:
        # --- oneof 対応 ---
        if f.containing_oneof is not None:
            oneof_name: str = f.containing_oneof.name
            selected: Optional[str] = req.WhichOneof(oneof_name)

            if selected != f.name:
                continue

            raw_sel: Any = getattr(req, f.name)

            if f.label == f.LABEL_REPEATED:
                kwargs[f.name] = [protobuf_to_python(x) for x in raw_sel]
            else:
                kwargs[f.name] = protobuf_to_python(raw_sel)

            continue

        # --- 通常フィールド ---
        raw: Any = getattr(req, f.name)

        if f.label == f.LABEL_REPEATED:
            kwargs[f.name] = [protobuf_to_python(x) for x in raw]
        else:
            kwargs[f.name] = protobuf_to_python(raw)

    return kwargs


def _has_varkw(
    sig: inspect.Signature,
) -> bool:
    """

    Args:
        sig:

    Returns:

    """
    for p in sig.parameters.values():
        if p.kind == p.VAR_KEYWORD:
            return True
    return False


def build_call_plan(
    ctrl_fn: Any,
    request: Any,
) -> CtrlCallPlan:
    """

    Args:
        ctrl_fn:
        request:

    Returns:

    """
    sig: inspect.Signature = inspect.signature(ctrl_fn)

    params: List[inspect.Parameter] = []
    for p in sig.parameters.values():
        if p.name == "self":
            continue
        params.append(p)

    kwargs: Dict[str, Any] = request_to_kwargs(request)
    positional: List[Any] = request_to_positional(request)

    # 追加ログ
    logger.debug("[DEBUG][CallPlan]")
    logger.debug("  ctrl_fn =", ctrl_fn)
    logger.debug("  signature =", sig)
    logger.debug("  params =", [p.name for p in params])
    logger.debug("  positional =", positional)
    logger.debug("  kwargs =", kwargs)

    has_varkw: bool = _has_varkw(sig)
    logger.debug("  has_varkw =", has_varkw)
    logger.debug("  len(params) =", len(params))
    logger.debug("  len(positional) =", len(positional))

    # # kwargs が存在する時点で positional 禁止
    # if kwargs:
    #     return CtrlCallPlan(args=(), kwargs=kwargs)

    # --- 必須 positional 引数を kwargs から昇格させる ---
    if kwargs and len(params) >= 1:
        p0 = params[0]

        if p0.name in kwargs:
            first = kwargs.pop(p0.name)

            logger.debug(
                "[build_call_plan] promote kwarg to positional:",
                p0.name,
                first,
            )

            return CtrlCallPlan(args=(first,), kwargs=kwargs)

        # 必須引数が kwargs に無い場合のみ kwargs 呼び
        return CtrlCallPlan(args=(), kwargs=kwargs)

    if has_varkw:
        return CtrlCallPlan(args=(), kwargs=kwargs)

    if len(params) == 0:
        return CtrlCallPlan(args=(), kwargs={})

    if len(params) == len(positional):
        logger.debug("[build_call_plan] USE positional ONLY:", positional)
        return CtrlCallPlan(args=tuple(positional), kwargs={})

    if len(params) == 1:
        logger.debug("[build_call_plan] USE positional + oneof:", positional)
        p0: inspect.Parameter = params[0]

        # positional が1つある場合は、それをそのまま使う
        if len(positional) == 1:
            logger.debug("[build_call_plan] USE positional == 1", positional)
            return CtrlCallPlan(args=(positional[0],), kwargs={})

        # positional が複数ある場合はまとめて1引数にする
        if len(positional) > 1:
            logger.debug("[build_call_plan] USE positional > 1", positional)
            return CtrlCallPlan(args=(positional,), kwargs={})

        # positional が無い場合は kwargs をそのまま渡す
        return CtrlCallPlan(args=(), kwargs=kwargs)

    # positional が存在しても、kwargs に oneof（pairs 等）が含まれる場合は
    # positional を使ってはいけない
    if len(positional) > 0:
        logger.debug(
            "[build_call_plan] positional EXISTS but fallback to kwargs",
            "positional=",
            positional,
            "kwargs=",
            kwargs,
        )
        # return CtrlCallPlan(args=tuple(positional), kwargs=kwargs)
        # return CtrlCallPlan(args=(), kwargs=kwargs)
        return CtrlCallPlan(args=tuple(positional), kwargs={})

    return CtrlCallPlan(args=(), kwargs=kwargs)


def build_dynamic_servicer_class(
    *,
    pb2: Any,
    pb2_grpc: Any,
    service_name: str,
) -> Type[Any]:
    """

    Args:
        pb2:
        pb2_grpc:
        service_name:

    Returns:

    """
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

                self._logger.info(
                    f"[GrpcServer][DEBUG] rpc={rpc_name_local}, request={request}"
                )

                try:
                    fn: Any = getattr(self._ctrl, ctrl_name_local)
                    plan = build_call_plan(fn, request)

                    self._logger.info(
                        f"[GrpcServer][DEBUG] call plan: args={plan.args}, kwargs={plan.kwargs}"
                    )

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
