#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class JsonBytes:
    """
    JSON を bytes として扱うための薄いラッパ。
    """

    data: bytes


def _to_json_compatible(obj: Any) -> Any:
    """
    JSON 直列化できる形へ正規化する。

    方針:
    - bytes は base64 へ変換してタグ付き dict にする
    - tuple は list に落とす
    - set は list に落とす
    - dict key は str へ（str でない場合は str()）
    - その他は json.dumps が受けられることを期待
    """
    if isinstance(obj, bytes):
        b64: str = base64.b64encode(obj).decode("ascii")
        return {"__type__": "bytes", "base64": b64}

    if isinstance(obj, tuple):
        out_list: List[Any] = []
        for x in obj:
            out_list.append(_to_json_compatible(x))
        return out_list

    if isinstance(obj, list):
        out_list2: List[Any] = []
        for x in obj:
            out_list2.append(_to_json_compatible(x))
        return out_list2

    if isinstance(obj, set):
        out_list3: List[Any] = []
        for x in obj:
            out_list3.append(_to_json_compatible(x))
        return out_list3

    if isinstance(obj, dict):
        out_dict: Dict[str, Any] = {}
        for k, v in obj.items():
            if isinstance(k, str):
                key_str: str = k
            else:
                key_str = str(k)
            out_dict[key_str] = _to_json_compatible(v)
        return out_dict

    return obj


def _from_json_compatible(obj: Any) -> Any:
    """
    _to_json_compatible の逆変換。
    """
    if isinstance(obj, list):
        out_list: List[Any] = []
        for x in obj:
            out_list.append(_from_json_compatible(x))
        return out_list

    if isinstance(obj, dict):
        type_tag: Any = obj.get("__type__")
        if type_tag == "bytes":
            b64: Any = obj.get("base64")
            if isinstance(b64, str):
                return base64.b64decode(b64.encode("ascii"))
            return b""

        out_dict: Dict[str, Any] = {}
        for k, v in obj.items():
            out_dict[k] = _from_json_compatible(v)
        return out_dict

    return obj


def dumps_json_bytes(value: Any) -> JsonBytes:
    """
    任意の Python 値を JSON bytes にする。
    """
    normalized: Any = _to_json_compatible(value)
    s: str = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    return JsonBytes(data=s.encode("utf-8"))


def loads_json_bytes(blob: bytes) -> Any:
    """
    JSON bytes から Python 値へ戻す。
    """
    s: str = blob.decode("utf-8")
    raw: Any = json.loads(s)
    return _from_json_compatible(raw)


def pack_args_kwargs(*args: Any, **kwargs: Any) -> Tuple[bytes, bytes]:
    """
    (*args, **kwargs) を (args_bytes, kwargs_bytes) にする。
    """
    args_list: List[Any] = list(args)
    kwargs_dict: Dict[str, Any] = dict(kwargs)
    args_b: bytes = dumps_json_bytes(args_list).data
    kwargs_b: bytes = dumps_json_bytes(kwargs_dict).data
    return args_b, kwargs_b


def unpack_args_kwargs(
    args_b: bytes, kwargs_b: bytes
) -> Tuple[List[Any], Dict[str, Any]]:
    """
    (args_bytes, kwargs_bytes) を (args_list, kwargs_dict) にする。
    """
    args_any: Any = loads_json_bytes(args_b)
    kwargs_any: Any = loads_json_bytes(kwargs_b)

    args_list: List[Any]
    kwargs_dict: Dict[str, Any]

    if isinstance(args_any, list):
        args_list = args_any
    else:
        args_list = [args_any]

    if isinstance(kwargs_any, dict):
        kwargs_dict = kwargs_any
    else:
        kwargs_dict = {}

    return args_list, kwargs_dict
