# grpc_frame/core.py
from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any, Dict, List, Optional, Tuple, Type


# ============================================================
# name mapping
# ============================================================


def camel_to_snake(name: str) -> str:
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


def snake_to_camel(name: str) -> str:
    parts: List[str] = name.split("_")
    out: List[str] = []
    for p in parts:
        if p == "":
            continue
        head: str = p[:1].upper()
        tail: str = p[1:]
        out.append(head + tail)
    return "".join(out)


def ctrl_method_to_rpc_name(ctrl_method: str) -> str:
    if ctrl_method == "":
        raise ValueError("empty ctrl_method")

    has_underscore: bool = False
    if "_" in ctrl_method:
        has_underscore = True

    if has_underscore is True:
        return snake_to_camel(ctrl_method)

    head: str = ctrl_method[:1].upper()
    tail: str = ctrl_method[1:]
    return head + tail


# ============================================================
# protobuf detection
# ============================================================


def is_protobuf_message(obj: Any) -> bool:
    desc: Any = getattr(obj, "DESCRIPTOR", None)
    if desc is None:
        return False

    has_fields: bool = hasattr(desc, "fields")
    if has_fields is False:
        return False

    return True


# ============================================================
# protobuf -> python (oneof reversible)
#   oneof: { oneof_name: { selected_field_name: value } }
# ============================================================


def protobuf_to_python(obj: Any) -> Any:
    if is_protobuf_message(obj) is False:
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


def request_to_kwargs(req: Any) -> Dict[str, Any]:
    desc: Any = req.DESCRIPTOR
    kwargs: Dict[str, Any] = {}

    oneofs: Any = getattr(desc, "oneofs", [])
    for oneof in oneofs:
        selected: Optional[str] = req.WhichOneof(oneof.name)
        if selected is None:
            continue
        kwargs[oneof.name] = {selected: protobuf_to_python(getattr(req, selected))}

    for field in desc.fields:
        if field.containing_oneof is not None:
            continue
        kwargs[field.name] = protobuf_to_python(getattr(req, field.name))

    return kwargs


def request_to_positional(req: Any) -> List[Any]:
    fields: List[Any] = list(req.DESCRIPTOR.fields)
    fields.sort(key=lambda f: int(f.number))

    values: List[Any] = []
    for f in fields:
        if f.containing_oneof is not None:
            continue

        raw: Any = getattr(req, f.name)

        is_repeated: bool = False
        if f.label == f.LABEL_REPEATED:
            is_repeated = True

        if is_repeated is True:
            tmp: List[Any] = []
            for x in raw:
                tmp.append(protobuf_to_python(x))
            values.append(tmp)
            continue

        values.append(protobuf_to_python(raw))

    return values


# ============================================================
# ctrl call planning
#   proto + signature から自動決定（従来ルール踏襲）
# ============================================================


@dataclass(frozen=True)
class CtrlCallPlan:
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]


def _has_varkw(sig: inspect.Signature) -> bool:
    for p in sig.parameters.values():
        if p.kind == p.VAR_KEYWORD:
            return True
    return False


def build_call_plan(ctrl_fn: Any, request: Any) -> CtrlCallPlan:
    sig: inspect.Signature = inspect.signature(ctrl_fn)

    params: List[inspect.Parameter] = []
    for p in sig.parameters.values():
        if p.name == "self":
            continue
        params.append(p)

    kwargs: Dict[str, Any] = request_to_kwargs(request)
    positional: List[Any] = request_to_positional(request)

    has_varkw: bool = _has_varkw(sig)
    if has_varkw is True:
        return CtrlCallPlan(args=(), kwargs=kwargs)

    if len(params) == 0:
        return CtrlCallPlan(args=(), kwargs={})

    if len(params) == len(positional):
        return CtrlCallPlan(args=tuple(positional), kwargs={})

    if len(params) == 1:
        if len(positional) == 0:
            if len(kwargs) == 0:
                return CtrlCallPlan(args=(), kwargs={})
            if len(kwargs) == 1:
                only_val: Any = next(iter(kwargs.values()))
                return CtrlCallPlan(args=(only_val,), kwargs={})
            return CtrlCallPlan(args=(), kwargs=kwargs)

        if len(positional) == 1:
            return CtrlCallPlan(args=(positional[0],), kwargs={})

        return CtrlCallPlan(args=(positional,), kwargs={})

    return CtrlCallPlan(args=(), kwargs=kwargs)


# ============================================================
# python -> protobuf message filling (descriptor-driven)
#   oneof input:
#     { oneof_name: { selected_field_name: value } }
# ============================================================


def fill_message(msg: Any, value: Any) -> None:
    if is_protobuf_message(msg) is False:
        return

    if isinstance(value, dict) is True:
        _fill_message_by_dict(msg, value)
        return

    if isinstance(value, list) is True:
        _fill_message_by_position(msg, value)
        return

    if isinstance(value, tuple) is True:
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


def _fill_message_by_dict(msg: Any, value: Dict[str, Any]) -> None:
    desc: Any = msg.DESCRIPTOR
    oneofs: Any = getattr(desc, "oneofs", [])

    # oneof: {oneof_name: {selected_field: val}}
    for oneof in oneofs:
        if oneof.name not in value:
            continue

        oneof_payload: Any = value[oneof.name]
        if isinstance(oneof_payload, dict) is False:
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
        if field.containing_oneof is not None:
            continue

        _set_field_by_value(msg, field, val)


def _set_field_by_value(msg: Any, field: Any, val: Any) -> None:
    is_repeated: bool = False
    if field.label == field.LABEL_REPEATED:
        is_repeated = True

    if is_repeated is True:
        if isinstance(val, list) is False:
            return

        container = getattr(msg, field.name)

        is_msg: bool = False
        if field.message_type is not None:
            is_msg = True

        if is_msg is False:
            container.extend(val)
            return

        for item in val:
            child = container.add()
            fill_message(child, item)
        return

    is_msg2: bool = False
    if field.message_type is not None:
        is_msg2 = True

    if is_msg2 is False:
        setattr(msg, field.name, val)
        return

    child2 = getattr(msg, field.name)
    fill_message(child2, val)


def _fill_message_by_position(msg: Any, values: List[Any]) -> None:
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

        _set_field_by_value(msg, field, v)


def build_request_message(request_cls: Type[Any], kwargs: Dict[str, Any]) -> Any:
    try:
        return request_cls(**kwargs)
    except Exception:
        pass

    req: Any = request_cls()
    fill_message(req, kwargs)
    return req


# ============================================================
# ctrl return -> response fill
# ============================================================


def fill_response_message(resp: Any, value: Any) -> Any:
    if value is None:
        return resp

    if isinstance(value, dict) is True:
        fill_message(resp, value)
        return resp

    fields: List[Any] = list(resp.DESCRIPTOR.fields)
    if len(fields) != 1:
        return resp

    f0: Any = fields[0]

    is_repeated: bool = False
    if f0.label == f0.LABEL_REPEATED:
        is_repeated = True

    if is_repeated is True:
        container = getattr(resp, f0.name)
        if isinstance(value, list) is True:
            container.extend(value)
        return resp

    is_msg: bool = False
    if f0.message_type is not None:
        is_msg = True

    if is_msg is False:
        setattr(resp, f0.name, value)
        return resp

    child = getattr(resp, f0.name)
    fill_message(child, value)
    return resp


def unwrap_response(resp: Any) -> Any:
    if is_protobuf_message(resp) is False:
        return resp

    has_ok: bool = hasattr(resp, "ok")
    if has_ok is True:
        ok_val: Any = getattr(resp, "ok")
        return bool(ok_val)

    return protobuf_to_python(resp)