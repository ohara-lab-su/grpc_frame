#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gRPC dispatch core (proto-driven, framework-agnostic)

このモジュールは「意味の層」です。
server / client / grpc という言葉を一切知らず、
protobuf descriptor と python の関数定義だけを扱います。

責務:
1. 名前写像 (ctrl <-> RPC)
2. protobuf -> python 変換
3. request -> ctrl 呼び出し計画の生成
4. ctrl 戻り値 -> response message 充填

設計原則:
- proto が API の唯一の制約
- ctrl は一般の Python API
- signature + descriptor から全て決める
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence, Tuple


# ------------------------------------------------------------
# name mapping
# ------------------------------------------------------------

def camel_to_snake(name: str) -> str:
    out: List[str] = []
    for ch in name:
        if ch.isupper():
            out.append("_")
            out.append(ch.lower())
        else:
            out.append(ch)
    s = "".join(out)
    return s[1:] if s.startswith("_") else s


def snake_to_camel(name: str) -> str:
    parts = name.split("_")
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def to_rpc_name(ctrl_method: str) -> str:
    if "_" in ctrl_method:
        return snake_to_camel(ctrl_method)
    return ctrl_method[:1].upper() + ctrl_method[1:]


# ------------------------------------------------------------
# protobuf detection
# ------------------------------------------------------------

def is_protobuf_message(obj: Any) -> bool:
    desc = getattr(obj, "DESCRIPTOR", None)
    if desc is None:
        return False
    return hasattr(desc, "fields")


# ------------------------------------------------------------
# protobuf -> python
# ------------------------------------------------------------

def protobuf_to_python(obj: Any) -> Any:
    if is_protobuf_message(obj) is False:
        return obj

    desc = obj.DESCRIPTOR
    out: Dict[str, Any] = {}

    for oneof in getattr(desc, "oneofs", []):
        selected = obj.WhichOneof(oneof.name)
        if selected is not None:
            out[oneof.name] = protobuf_to_python(getattr(obj, selected))

    for field in desc.fields:
        if field.containing_oneof is not None:
            continue
        value = getattr(obj, field.name)

        if field.label == field.LABEL_REPEATED:
            out[field.name] = [protobuf_to_python(x) for x in value]
        elif field.message_type is not None:
            out[field.name] = protobuf_to_python(value)
        else:
            out[field.name] = value

    return out


def request_to_kwargs(req: Any) -> Dict[str, Any]:
    desc = req.DESCRIPTOR
    kwargs: Dict[str, Any] = {}

    for oneof in getattr(desc, "oneofs", []):
        selected = req.WhichOneof(oneof.name)
        if selected is not None:
            kwargs[oneof.name] = protobuf_to_python(getattr(req, selected))

    for field in desc.fields:
        if field.containing_oneof is None:
            kwargs[field.name] = protobuf_to_python(getattr(req, field.name))

    return kwargs


def request_to_positional(req: Any) -> List[Any]:
    fields = sorted(req.DESCRIPTOR.fields, key=lambda f: f.number)
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


# ------------------------------------------------------------
# ctrl call planning
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# response filling
# ------------------------------------------------------------

def fill_response_message(resp: Any, value: Any) -> Any:
    if value is None:
        return resp

    if isinstance(value, dict):
        for k, v in value.items():
            field = resp.DESCRIPTOR.fields_by_name.get(k)
            if field is None:
                continue
            if field.label == field.LABEL_REPEATED:
                container = getattr(resp, k)
                if field.message_type is None:
                    container.extend(v)
                else:
                    for item in v:
                        child = container.add()
                        fill_response_message(child, item)
            elif field.message_type is None:
                setattr(resp, k, v)
            else:
                fill_response_message(getattr(resp, k), v)
        return resp

    fields = resp.DESCRIPTOR.fields
    if len(fields) == 1:
        f = fields[0]
        if f.label == f.LABEL_REPEATED:
            getattr(resp, f.name).extend(value)
        elif f.message_type is None:
            setattr(resp, f.name, value)
        else:
            fill_response_message(getattr(resp, f.name), value)
        return resp

    return resp