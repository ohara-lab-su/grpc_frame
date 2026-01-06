#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import inspect
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Type


# ============================================================
# name mapping
# ============================================================

def camel_to_snake(name: str) -> str:
    out: List[str] = []
    for c in name:
        if c.isupper():
            out.append("_")
            out.append(c.lower())
        else:
            out.append(c)
    s = "".join(out)
    return s[1:] if s.startswith("_") else s


def snake_to_camel(name: str) -> str:
    return "".join(p[:1].upper() + p[1:] for p in name.split("_") if p)


def to_rpc_name(ctrl_method: str) -> str:
    if "_" in ctrl_method:
        return snake_to_camel(ctrl_method)
    return ctrl_method[:1].upper() + ctrl_method[1:]


# ============================================================
# protobuf utilities
# ============================================================

def is_protobuf_message(obj: Any) -> bool:
    return hasattr(obj, "DESCRIPTOR") and hasattr(obj.DESCRIPTOR, "fields")


def protobuf_to_python(obj: Any) -> Any:
    if not is_protobuf_message(obj):
        return obj

    desc = obj.DESCRIPTOR
    out: Dict[str, Any] = {}

    for oneof in getattr(desc, "oneofs", []):
        sel = obj.WhichOneof(oneof.name)
        if sel is not None:
            out[oneof.name] = protobuf_to_python(getattr(obj, sel))

    for field in desc.fields:
        if field.containing_oneof is not None:
            continue
        val = getattr(obj, field.name)
        if field.label == field.LABEL_REPEATED:
            out[field.name] = [protobuf_to_python(x) for x in val]
        elif field.message_type is not None:
            out[field.name] = protobuf_to_python(val)
        else:
            out[field.name] = val

    return out


# ============================================================
# request handling
# ============================================================

def request_to_kwargs(req: Any) -> Dict[str, Any]:
    desc = req.DESCRIPTOR
    kwargs: Dict[str, Any] = {}

    for oneof in getattr(desc, "oneofs", []):
        sel = req.WhichOneof(oneof.name)
        if sel is not None:
            kwargs[oneof.name] = protobuf_to_python(getattr(req, sel))

    for field in desc.fields:
        if field.containing_oneof is None:
            kwargs[field.name] = protobuf_to_python(getattr(req, field.name))

    return kwargs


def request_to_positional(req: Any) -> List[Any]:
    fields = sorted(req.DESCRIPTOR.fields, key=lambda f: int(f.number))
    values: List[Any] = []

    for f in fields:
        if f.containing_oneof is not None:
            continue
        val = getattr(req, f.name)
        if f.label == f.LABEL_REPEATED:
            values.append([protobuf_to_python(x) for x in val])
        else:
            values.append(protobuf_to_python(val))

    return values


# ============================================================
# ctrl call planning
# ============================================================

@dataclass(frozen=True)
class CtrlCallPlan:
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]


def build_call_plan(ctrl_fn: Any, request: Any) -> CtrlCallPlan:
    sig = inspect.signature(ctrl_fn)
    params = [p for p in sig.parameters.values() if p.name != "self"]

    kwargs = request_to_kwargs(request)
    positional = request_to_positional(request)

    if any(p.kind == p.VAR_KEYWORD for p in params):
        return CtrlCallPlan(args=(), kwargs=kwargs)

    if len(params) == 0:
        return CtrlCallPlan(args=(), kwargs={})

    if len(params) == len(positional):
        return CtrlCallPlan(args=tuple(positional), kwargs={})

    if len(params) == 1:
        if len(positional) == 1:
            return CtrlCallPlan(args=(positional[0],), kwargs={})
        return CtrlCallPlan(args=(positional,), kwargs={})

    return CtrlCallPlan(args=(), kwargs=kwargs)


# ============================================================
# message filling
# ============================================================

def fill_message(msg: Any, value: Any) -> None:
    if not is_protobuf_message(msg):
        return

    if isinstance(value, dict):
        for k, v in value.items():
            field = msg.DESCRIPTOR.fields_by_name.get(k)
            if field is None:
                continue
            if field.label == field.LABEL_REPEATED:
                container = getattr(msg, k)
                if field.message_type is None:
                    container.extend(v)
                else:
                    for item in v:
                        child = container.add()
                        fill_message(child, item)
            elif field.message_type is None:
                setattr(msg, k, v)
            else:
                fill_message(getattr(msg, k), v)
        return

    fields = msg.DESCRIPTOR.fields
    if len(fields) != 1:
        return

    f = fields[0]
    if f.label == f.LABEL_REPEATED:
        getattr(msg, f.name).extend(value)
    elif f.message_type is None:
        setattr(msg, f.name, value)
    else:
        fill_message(getattr(msg, f.name), value)


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
    fill_message(resp, value)
    return resp


def unwrap_response(resp: Any) -> Any:
    if not is_protobuf_message(resp):
        return resp
    if hasattr(resp, "ok"):
        return bool(resp.ok)
    return protobuf_to_python(resp)