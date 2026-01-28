#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import base64
import json
from dataclasses import is_dataclass, asdict
from typing import Any, Dict, List, Tuple


_BYTES_TAG: str = "__bytes__"
_TUPLE_TAG: str = "__tuple__"


def _to_jsonable(obj: Any) -> Any:
    if obj is None:
        return None

    if isinstance(obj, (bool, int, float, str)):
        return obj

    if isinstance(obj, bytes):
        b64: str = base64.b64encode(obj).decode("ascii")
        return {_BYTES_TAG: b64}

    if is_dataclass(obj):
        return _to_jsonable(asdict(obj))

    if isinstance(obj, tuple):
        tmp: List[Any] = []
        for x in obj:
            tmp.append(_to_jsonable(x))
        return {_TUPLE_TAG: tmp}

    if isinstance(obj, list):
        tmp2: List[Any] = []
        for x2 in obj:
            tmp2.append(_to_jsonable(x2))
        return tmp2

    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            out[str(k)] = _to_jsonable(v)
        return out

    return str(obj)


def _from_jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        if _BYTES_TAG in obj:
            b64 = obj[_BYTES_TAG]
            if isinstance(b64, str):
                return base64.b64decode(b64.encode("ascii"))
            return b""

        if _TUPLE_TAG in obj:
            raw = obj[_TUPLE_TAG]
            if isinstance(raw, list):
                tmp: List[Any] = []
                for x in raw:
                    tmp.append(_from_jsonable(x))
                return tuple(tmp)
            return tuple()

        out2: Dict[str, Any] = {}
        for k2, v2 in obj.items():
            out2[str(k2)] = _from_jsonable(v2)
        return out2

    if isinstance(obj, list):
        tmp2: List[Any] = []
        for x2 in obj:
            tmp2.append(_from_jsonable(x2))
        return tmp2

    return obj


def pack_args(args: Tuple[Any, ...]) -> bytes:
    tmp: List[Any] = []
    for x in args:
        tmp.append(_to_jsonable(x))
    payload: Dict[str, Any] = {"args": tmp}
    s: str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return s.encode("utf-8")


def pack_kwargs(kwargs: Dict[str, Any]) -> bytes:
    out: Dict[str, Any] = {}
    for k, v in kwargs.items():
        out[str(k)] = _to_jsonable(v)
    payload: Dict[str, Any] = {"kwargs": out}
    s: str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return s.encode("utf-8")


def unpack_args(args_json: bytes) -> List[Any]:
    if args_json is None:
        return []
    if len(args_json) == 0:
        return []

    raw: Any = json.loads(args_json.decode("utf-8"))
    if not isinstance(raw, dict):
        return []

    args = raw.get("args")
    if not isinstance(args, list):
        return []

    out: List[Any] = []
    for x in args:
        out.append(_from_jsonable(x))
    return out


def unpack_kwargs(kwargs_json: bytes) -> Dict[str, Any]:
    if kwargs_json is None:
        return {}
    if len(kwargs_json) == 0:
        return {}

    raw: Any = json.loads(kwargs_json.decode("utf-8"))
    if not isinstance(raw, dict):
        return {}

    kwargs = raw.get("kwargs")
    if not isinstance(kwargs, dict):
        return {}

    out: Dict[str, Any] = {}
    for k, v in kwargs.items():
        out[str(k)] = _from_jsonable(v)
    return out


def pack_result(result: Any) -> bytes:
    payload: Dict[str, Any] = {"result": _to_jsonable(result)}
    s: str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return s.encode("utf-8")


def unpack_result(result_json: bytes) -> Any:
    if result_json is None:
        return None
    if len(result_json) == 0:
        return None

    raw: Any = json.loads(result_json.decode("utf-8"))
    if not isinstance(raw, dict):
        return None

    return _from_jsonable(raw.get("result"))
