# grpc_frame/core.py
from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any, Dict, List, Optional, Tuple, Type

from x_logger import XLogger

logger = XLogger(log_level="debug")

# ============================================================
# name mapping
# ============================================================


def camel_to_snake(
    name: str,
) -> str:
    """

    Args:
        name:

    Returns:

    """
    out: List[str] = []
    for ch in name:
        if ch.isupper():
            out.append("_")
            out.append(ch.lower())
        else:
            out.append(ch)

    s: str = "".join(out)
    if s.startswith("_"):
        return s[1:]
    return s


def snake_to_camel(
    name: str,
) -> str:
    """

    Args:
        name:

    Returns:

    """
    parts: List[str] = name.split("_")
    out: List[str] = []
    for p in parts:
        if p == "":
            continue
        head: str = p[:1].upper()
        tail: str = p[1:]
        out.append(head + tail)
    return "".join(out)


def ctrl_method_to_rpc_name(
    ctrl_method: str,
) -> str:
    """

    Args:
        ctrl_method:

    Returns:

    """
    if ctrl_method == "":
        raise ValueError("empty ctrl_method")

    has_underscore: bool = False
    if "_" in ctrl_method:
        has_underscore = True

    if has_underscore:
        return snake_to_camel(ctrl_method)

    head: str = ctrl_method[:1].upper()
    tail: str = ctrl_method[1:]
    return head + tail


# ============================================================
# protobuf detection
# ============================================================


def is_protobuf_message(
    obj: Any,
) -> bool:
    """

    Args:
        obj:

    Returns:

    """
    desc: Any = getattr(obj, "DESCRIPTOR", None)
    if desc is None:
        return False

    has_fields: bool = hasattr(desc, "fields")
    if not has_fields:
        return False

    return True


# ============================================================
# protobuf -> python (oneof reversible)
#   oneof: { oneof_name: { selected_field_name: value } }
# ============================================================


def protobuf_to_python(
    obj: Any,
) -> Any:
    """

    Args:
        obj:

    Returns:

    """
    if not is_protobuf_message(obj):
        return obj

    desc: Any = obj.DESCRIPTOR
    out: Dict[str, Any] = {}

    oneofs: Any = getattr(desc, "oneofs", [])
    for oneof in oneofs:
        selected: Optional[str] = obj.WhichOneof(oneof.name)
        if selected is None:
            continue
        selected_val: Any = getattr(obj, selected)
        out[oneof.name] = {selected: protobuf_to_python(selected_val)}

    for field in desc.fields:
        if field.containing_oneof is not None:
            continue

        raw: Any = getattr(obj, field.name)

        is_repeated: bool = False
        if field.label == field.LABEL_REPEATED:
            is_repeated = True

        if is_repeated is True:
            tmp: List[Any] = []
            for x in raw:
                tmp.append(protobuf_to_python(x))
            out[field.name] = tmp
            continue

        is_message: bool = False
        if field.message_type is not None:
            is_message = True

        if is_message is True:
            out[field.name] = protobuf_to_python(raw)
            continue

        out[field.name] = raw

    return out


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


def request_to_positional(
    req: Any,
) -> List[Any]:
    """

    Args:
        req:

    Returns:

    """
    logger.debug("[request_to_positional] req =", req)

    fields: List[Any] = list(req.DESCRIPTOR.fields)
    fields.sort(key=lambda f: int(f.number))

    values: List[Any] = []
    for f in fields:
        logger.debug(
            "[request_to_positional] field:",
            f.name,
            "number=",
            f.number,
            "oneof=",
            f.containing_oneof.name if f.containing_oneof else None,
            "label=",
            f.label,
        )
        # if f.containing_oneof is not None:
        #     continue
        if f.containing_oneof is not None:
            oneof_name: str = f.containing_oneof.name

            selected: Optional[str] = req.WhichOneof(oneof_name)
            if selected is None:
                continue
            if selected != f.name:
                continue

            raw_sel: Any = getattr(req, f.name)

            logger.debug(
                "[request_to_positional][oneof]",
                "oneof=",
                oneof_name,
                "selected=",
                f.name,
                "raw=",
                raw_sel,
            )

            if f.label == f.LABEL_REPEATED:
                tmp_sel: List[Any] = []
                for x in raw_sel:
                    tmp_sel.append(protobuf_to_python(x))

                logger.debug("[request_to_positional] append value =", tmp_sel)
                values.append(tmp_sel)
            else:
                logger.debug("[request_to_positional] append value =", raw_sel)
                values.append(protobuf_to_python(raw_sel))

            continue

        raw: Any = getattr(req, f.name)

        is_repeated: bool = False
        if f.label == f.LABEL_REPEATED:
            is_repeated = True

        if is_repeated:
            tmp: List[Any] = []
            for x in raw:
                tmp.append(protobuf_to_python(x))
            values.append(tmp)
            continue

        values.append(protobuf_to_python(raw))

    logger.debug("[request_to_positional] result values =", values)
    return values


# ============================================================
# ctrl call planning
#   proto + signature から自動決定（従来ルール踏襲）
# ============================================================


@dataclass(frozen=True)
class CtrlCallPlan:
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]


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

    if has_varkw:
        return CtrlCallPlan(args=(), kwargs=kwargs)

    if len(params) == 0:
        return CtrlCallPlan(args=(), kwargs={})

    if len(params) == len(positional):
        logger.debug("[build_call_plan] USE positional ONLY:", positional)
        return CtrlCallPlan(args=tuple(positional), kwargs={})

    if len(params) == 1:
        p0: inspect.Parameter = params[0]

        # positional が1つある場合は、それをそのまま使う
        if len(positional) == 1:
            return CtrlCallPlan(args=(positional[0],), kwargs={})

        # positional が複数ある場合はまとめて1引数にする
        if len(positional) > 1:
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
        return CtrlCallPlan(args=(), kwargs=kwargs)

    return CtrlCallPlan(args=(), kwargs=kwargs)


# ============================================================
# python -> protobuf message filling (descriptor-driven)
#   oneof input:
#     { oneof_name: { selected_field_name: value } }
# ============================================================


def fill_message(
    msg: Any,
    value: Any,
) -> None:
    """

    Args:
        msg:
        value:

    Returns:

    """
    if not is_protobuf_message(msg):
        return

    if isinstance(value, dict):
        logger.debug("[fill_message] (dict) by POSITION:", value)
        _fill_message_by_dict(msg, value)
        return

    if isinstance(value, list):
        logger.debug("[fill_message] (list) by POSITION:", value)
        _fill_message_by_position(msg, value)
        return

    if isinstance(value, tuple):
        logger.debug("[fill_message] (tuple) by POSITION:", value)
        _fill_message_by_position(msg, list(value))
        return

    fields: List[Any] = list(msg.DESCRIPTOR.fields)
    if len(fields) != 1:
        return

    f0: Any = fields[0]

    is_repeated: bool = False
    if f0.label == f0.LABEL_REPEATED:
        is_repeated = True

    if is_repeated is True:
        container = getattr(msg, f0.name)
        if isinstance(value, list) is True:
            container.extend(value)
        return

    is_msg: bool = False
    if f0.message_type is not None:
        is_msg = True

    if is_msg is False:
        setattr(msg, f0.name, value)
        return

    child = getattr(msg, f0.name)
    fill_message(child, value)


def _fill_message_by_dict(
    msg: Any,
    value: Dict[str, Any],
) -> None:
    """

    Args:
        msg:
        value:

    Returns:

    """
    desc: Any = msg.DESCRIPTOR
    oneofs: Any = getattr(desc, "oneofs", [])

    # oneof: {oneof_name: {selected_field: val}}
    for oneof in oneofs:
        if oneof.name not in value:
            continue

        oneof_payload: Any = value[oneof.name]
        if not isinstance(oneof_payload, dict):
            continue

        if len(oneof_payload) != 1:
            continue

        selected_field_name: str = next(iter(oneof_payload.keys()))
        selected_value: Any = oneof_payload[selected_field_name]

        field_obj: Any = desc.fields_by_name.get(selected_field_name)
        if field_obj is None:
            continue

        if field_obj.containing_oneof is None:
            continue

        if field_obj.containing_oneof.name != oneof.name:
            continue

        _set_field_by_value(msg, field_obj, selected_value)

    # normal fields
    for key, val in value.items():
        is_oneof_key: bool = False
        for oneof in oneofs:
            if key == oneof.name:
                is_oneof_key = True
                break
        if is_oneof_key is True:
            continue

        field: Any = desc.fields_by_name.get(key)
        if field is None:
            continue
        # if field.containing_oneof is not None:
        #     continue

        _set_field_by_value(msg, field, val)


def _set_field_by_value(
    msg: Any,
    field: Any,
    val: Any,
) -> None:
    """

    Args:
        msg:
        field:
        val:

    Returns:

    """
    is_repeated: bool = False
    if field.label == field.LABEL_REPEATED:
        is_repeated = True

    if is_repeated:
        if not isinstance(val, list):
            return

        container = getattr(msg, field.name)

        is_msg: bool = False
        if field.message_type is not None:
            is_msg = True

        if not is_msg:
            container.extend(val)
            return

        for item in val:
            child = container.add()
            fill_message(child, item)
        return

    is_msg2: bool = False
    if field.message_type is not None:
        is_msg2 = True

    if not is_msg2:
        setattr(msg, field.name, val)
        return

    child2 = getattr(msg, field.name)
    fill_message(child2, val)


def _fill_message_by_position(
    msg: Any,
    values: List[Any],
) -> None:
    """

    Args:
        msg:
        values:

    Returns:

    """
    logger.debug("[fill_message] msg =", msg)
    logger.debug("[fill_message] value =", value)

    fields: List[Any] = list(msg.DESCRIPTOR.fields)
    fields.sort(key=lambda f: int(f.number))

    index: int = 0
    for field in fields:
        if field.containing_oneof is not None:
            continue

        if index >= len(values):
            break

        v: Any = values[index]
        index += 1

        logger.debug(
            "[fill_message] set field",
            "field=",
            field.name,
            "value=",
            val,
        )
        _set_field_by_value(msg, field, v)


def build_request_message(
    request_cls: Type[Any],
    kwargs: Dict[str, Any],
) -> Any:
    """

    Args:
        request_cls:
        kwargs:

    Returns:

    """
    logger.debug("[DEBUG][build_request_message] BEGIN")
    logger.debug("  request_cls =", request_cls)
    logger.debug("  input kwargs =", kwargs)
    try:
        logger.debug("[DEBUG][build_request_message] try: calling constructor")
        return request_cls(**kwargs)
    except Exception as e:
        logger.debug("[DEBUG][build_request_message] constructor FAILED:", e)

    req: Any = request_cls()
    logger.debug(
        "[DEBUG][build_request_message] fallback: empty request created =", req
    )

    fill_message(req, kwargs)

    logger.debug("[DEBUG][build_request_message] after fill_message =", req)
    logger.debug("[DEBUG][build_request_message] END")
    return req


# ============================================================
# ctrl return -> response fill
# ============================================================


def fill_response_message(
    resp: Any,
    value: Any,
) -> Any:
    """

    Args:
        resp:
        value:

    Returns:

    """
    if value is None:
        return resp

    if isinstance(value, dict):
        fill_message(resp, value)
        return resp

    fields: List[Any] = list(resp.DESCRIPTOR.fields)
    if len(fields) != 1:
        return resp

    f0: Any = fields[0]

    is_repeated: bool = False
    if f0.label == f0.LABEL_REPEATED:
        is_repeated = True

    if is_repeated:
        container = getattr(resp, f0.name)
        if isinstance(value, list):
            container.extend(value)
        return resp

    is_msg: bool = False
    if f0.message_type is not None:
        is_msg = True

    if not is_msg:
        setattr(resp, f0.name, value)
        return resp

    child = getattr(resp, f0.name)
    fill_message(child, value)
    return resp


def unwrap_response(
    resp: Any,
) -> Any:
    """

    Args:
        resp:

    Returns:

    """
    if not is_protobuf_message(resp):
        return resp

    has_ok: bool = hasattr(resp, "ok")
    if has_ok:
        ok_val: Any = getattr(resp, "ok")
        return bool(ok_val)

    return protobuf_to_python(resp)
