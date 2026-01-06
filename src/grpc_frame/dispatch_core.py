#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
grpc_dispatch_core.py

gRPC dispatch core (proto-driven, framework-agnostic)

このモジュールは「意味の層」です。
server / client / grpc という言葉を一切知らず、
protobuf descriptor と python の関数定義だけを扱います。

責務:
1. 名前写像 (ctrl <-> RPC)
2. protobuf -> python 変換
3. request -> ctrl 呼び出し計画の生成
4. ctrl 戻り値 -> response message 充填
5. python 値 -> request message 充填（descriptor 駆動）

設計原則:
- proto が API の唯一の制約
- ctrl は一般の Python API
- signature + descriptor から全て決める
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
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


def to_rpc_name(ctrl_method: str) -> str:
    has_underscore: bool = False
    if "_" in ctrl_method:
        has_underscore = True

    if has_underscore is True:
        return snake_to_camel(ctrl_method)

    if ctrl_method == "":
        raise ValueError("empty ctrl_method")

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
# protobuf -> python
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
        out[oneof.name] = protobuf_to_python(selected_val)

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
        kwargs[oneof.name] = protobuf_to_python(getattr(req, selected))

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

    if _has_varkw(sig) is True:
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
# ============================================================


def fill_message(msg: Any, value: Any) -> None:
    """
    protobuf message に python 値を流し込む（message 自体を置換しない）。

    value の許容:
    - dict: field 名で対応付け
    - list/tuple: proto field number 順で対応付け
    - scalar: message が 1 フィールドのときだけ流し込む
    """
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

    is_message: bool = False
    if f0.message_type is not None:
        is_message = True

    if is_message is False:
        setattr(msg, f0.name, value)
        return

    child = getattr(msg, f0.name)
    fill_message(child, value)


def _fill_message_by_dict(msg: Any, value: Dict[str, Any]) -> None:
    for key, val in value.items():
        field: Any = msg.DESCRIPTOR.fields_by_name.get(key)
        if field is None:
            continue

        is_repeated: bool = False
        if field.label == field.LABEL_REPEATED:
            is_repeated = True

        if is_repeated is True:
            container = getattr(msg, key)
            if isinstance(val, list) is False:
                continue

            is_msg: bool = False
            if field.message_type is not None:
                is_msg = True

            if is_msg is False:
                container.extend(val)
                continue

            for item in val:
                child = container.add()
                fill_message(child, item)
            continue

        is_msg2: bool = False
        if field.message_type is not None:
            is_msg2 = True

        if is_msg2 is False:
            setattr(msg, key, val)
            continue

        child2 = getattr(msg, key)
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

        is_repeated: bool = False
        if field.label == field.LABEL_REPEATED:
            is_repeated = True

        if is_repeated is True:
            container = getattr(msg, field.name)
            if isinstance(v, list) is False:
                continue

            is_msg: bool = False
            if field.message_type is not None:
                is_msg = True

            if is_msg is False:
                container.extend(v)
                continue

            for item in v:
                child = container.add()
                fill_message(child, item)
            continue

        is_msg2: bool = False
        if field.message_type is not None:
            is_msg2 = True

        if is_msg2 is False:
            setattr(msg, field.name, v)
            continue

        child2 = getattr(msg, field.name)
        fill_message(child2, v)


def build_request_message(request_cls: Type[Any], kwargs: Dict[str, Any]) -> Any:
    """
    request_cls から request message を構築する。

    原則:
    - request_cls(**kwargs) が通ればそれを優先
    - 通らない場合は descriptor 駆動でフィールドへ詰める
    """
    try:
        return request_cls(**kwargs)
    except Exception:
        pass

    req: Any = request_cls()
    fill_message(req, kwargs)
    return req


# ============================================================
# ctrl return -> response message filling (descriptor-driven)
# ============================================================


def fill_response_message(resp: Any, value: Any) -> Any:
    """
    ctrl 戻り値（python 値）を response protobuf に詰める。

    value の許容:
    - None: 何も詰めず resp を返す
    - dict: フィールド名で詰める（message/repeated も descriptor 駆動）
    - 非 dict: response が 1 フィールドのときだけ詰める
    """
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
    """
    response を python 値へ正規化する。

    ルール:
    - ok フィールドがあれば bool
    - それ以外は protobuf_to_python を返す
    """
    if is_protobuf_message(resp) is False:
        return resp

    has_ok: bool = hasattr(resp, "ok")
    if has_ok is True:
        ok_val: Any = getattr(resp, "ok")
        return bool(ok_val)

    return protobuf_to_python(resp)