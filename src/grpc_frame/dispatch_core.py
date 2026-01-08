from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any, Dict, List, Optional, Tuple, Type


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
        out.append(p[:1].upper() + p[1:])
    return "".join(out)


def ctrl_method_to_rpc_name(ctrl_method: str) -> str:
    if ctrl_method == "":
        raise ValueError("empty ctrl_method")

    if "_" in ctrl_method:
        return snake_to_camel(ctrl_method)

    return ctrl_method[:1].upper() + ctrl_method[1:]


def is_protobuf_message(obj: Any) -> bool:
    desc: Any = getattr(obj, "DESCRIPTOR", None)
    if desc is None:
        return False
    return hasattr(desc, "fields")


def _is_number(obj: Any) -> bool:
    if isinstance(obj, bool):
        return False
    return isinstance(obj, (int, float))


def _is_scalar(obj: Any) -> bool:
    return (
        _is_number(obj)
        or isinstance(obj, str)
        or isinstance(obj, bytes)
        or isinstance(obj, bool)
    )


def _field_names_of_message_cls(message_cls: Type[Any]) -> List[str]:
    try:
        desc: Any = getattr(message_cls, "DESCRIPTOR", None)
        if desc is None:
            return []
        return [f.name for f in desc.fields]
    except Exception:
        return []


def _message_cls_of_field(field: Any) -> Optional[Type[Any]]:
    try:
        msg_type: Any = getattr(field, "message_type", None)
        if msg_type is None:
            return None
        return getattr(msg_type, "_concrete_class", None)
    except Exception:
        return None


def protobuf_to_python(obj: Any) -> Any:
    if not is_protobuf_message(obj):
        return obj

    desc: Any = obj.DESCRIPTOR
    out: Dict[str, Any] = {}

    for oneof in getattr(desc, "oneofs", []):
        selected = obj.WhichOneof(oneof.name)
        if selected is not None:
            out[oneof.name] = protobuf_to_python(getattr(obj, selected))

    for field in desc.fields:
        if field.containing_oneof is not None:
            continue

        raw = getattr(obj, field.name)

        if field.label == field.LABEL_REPEATED:
            out[field.name] = [protobuf_to_python(x) for x in raw]
            continue

        if field.message_type is not None:
            out[field.name] = protobuf_to_python(raw)
            continue

        out[field.name] = raw

    return out


def request_to_kwargs(req: Any) -> Dict[str, Any]:
    desc: Any = req.DESCRIPTOR
    kwargs: Dict[str, Any] = {}

    for oneof in getattr(desc, "oneofs", []):
        selected = req.WhichOneof(oneof.name)
        if selected is not None:
            kwargs[oneof.name] = protobuf_to_python(getattr(req, selected))

    for field in desc.fields:
        if field.containing_oneof is not None:
            continue
        kwargs[field.name] = protobuf_to_python(getattr(req, field.name))

    return kwargs


def request_to_positional(req: Any) -> List[Any]:
    fields = sorted(req.DESCRIPTOR.fields, key=lambda f: int(f.number))
    values: List[Any] = []

    for f in fields:
        if f.containing_oneof is not None:
            continue

        raw = getattr(req, f.name)
        if f.label == f.LABEL_REPEATED:
            values.append([protobuf_to_python(x) for x in raw])
        else:
            values.append(protobuf_to_python(raw))

    return values


@dataclass(frozen=True)
class CtrlCallPlan:
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]


def _has_varkw(sig: inspect.Signature) -> bool:
    return any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values())


def build_call_plan(ctrl_fn: Any, request: Any) -> CtrlCallPlan:
    sig = inspect.signature(ctrl_fn)

    params = [p for p in sig.parameters.values() if p.name != "self"]

    kwargs = request_to_kwargs(request)
    positional = request_to_positional(request)

    if _has_varkw(sig):
        return CtrlCallPlan(args=(), kwargs=kwargs)

    if len(params) == 0:
        return CtrlCallPlan(args=(), kwargs={})

    if len(params) == len(positional):
        return CtrlCallPlan(args=tuple(positional), kwargs={})

    if len(params) == 1:
        if len(positional) == 0:
            if len(kwargs) == 1:
                return CtrlCallPlan(args=(next(iter(kwargs.values())),), kwargs={})
            return CtrlCallPlan(args=(), kwargs=kwargs)

        if len(positional) == 1:
            return CtrlCallPlan(args=(positional[0],), kwargs={})

        return CtrlCallPlan(args=(positional,), kwargs={})

    return CtrlCallPlan(args=(), kwargs=kwargs)


def fill_message(msg: Any, value: Any) -> None:
    if not is_protobuf_message(msg):
        return

    if isinstance(value, dict):
        _fill_message_by_dict(msg, value)
        return

    if isinstance(value, (list, tuple)):
        _fill_message_by_position(msg, list(value))
        return

    fields = list(msg.DESCRIPTOR.fields)
    if len(fields) != 1:
        return

    f0 = fields[0]
    if f0.label == f0.LABEL_REPEATED:
        getattr(msg, f0.name).extend(value)
        return

    if f0.message_type is None:
        setattr(msg, f0.name, value)
        return

    fill_message(getattr(msg, f0.name), value)


def _fill_message_by_dict(msg: Any, value: Dict[str, Any]) -> None:
    desc = msg.DESCRIPTOR

    for key, val in value.items():
        field = desc.fields_by_name.get(key)
        if field is None:
            continue
        _set_field_by_value(msg, field, val)


def _set_field_by_value(msg: Any, field: Any, val: Any) -> None:
    if field.label == field.LABEL_REPEATED:
        container = getattr(msg, field.name)
        if field.message_type is None:
            container.extend(val)
        else:
            for item in val:
                child = container.add()
                fill_message(child, item)
        return

    if field.message_type is None:
        setattr(msg, field.name, val)
        return

    fill_message(getattr(msg, field.name), val)


def _fill_message_by_position(msg: Any, values: List[Any]) -> None:
    fields = sorted(msg.DESCRIPTOR.fields, key=lambda f: int(f.number))
    idx = 0
    for f in fields:
        if f.containing_oneof is not None:
            continue
        if idx >= len(values):
            break
        _set_field_by_value(msg, f, values[idx])
        idx += 1


def build_request_message(request_cls: Type[Any], kwargs: Dict[str, Any]) -> Any:
    try:
        return request_cls(**kwargs)
    except Exception:
        req = request_cls()
        fill_message(req, kwargs)
        return req


def fill_response_message(resp: Any, value: Any) -> Any:
    if value is None:
        return resp

    if isinstance(value, dict):
        fill_message(resp, value)
        return resp

    fields = list(resp.DESCRIPTOR.fields)
    if len(fields) != 1:
        return resp

    f0 = fields[0]
    if f0.label == f0.LABEL_REPEATED:
        getattr(resp, f0.name).extend(value)
        return resp

    if f0.message_type is None:
        setattr(resp, f0.name, value)
        return resp

    fill_message(getattr(resp, f0.name), value)
    return resp


def unwrap_response(resp: Any) -> Any:
    if not is_protobuf_message(resp):
        return resp

    if hasattr(resp, "ok"):
        return bool(getattr(resp, "ok"))

    return protobuf_to_python(resp)
