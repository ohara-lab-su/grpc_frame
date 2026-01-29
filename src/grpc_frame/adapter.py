#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import base64
import json
import pickle
from typing import Any, Dict, Tuple


_JSON_MAGIC: bytes = b"J"
_PICKLE_MAGIC: bytes = b"P"


class _BytesJsonEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, (bytes, bytearray)):
            b64: str = base64.b64encode(bytes(obj)).decode("ascii")
            return {"__bytes__": b64}
        return json.JSONEncoder.default(self, obj)


def _bytes_json_object_hook(d: Dict[str, Any]) -> Any:
    if "__bytes__" in d:
        b64 = d["__bytes__"]
        if isinstance(b64, str):
            return base64.b64decode(b64.encode("ascii"))
    return d


def _try_json_dumps(obj: Any) -> bytes:
    try:
        s: str = json.dumps(
            obj,
            cls=_BytesJsonEncoder,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return _JSON_MAGIC + s.encode("utf-8")
    except Exception:
        pass

    payload: bytes = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    return _PICKLE_MAGIC + payload


def _loads(payload: bytes) -> Any:
    if payload is None:
        return None
    if len(payload) == 0:
        return None

    magic: bytes = payload[:1]
    body: bytes = payload[1:]

    if magic == _JSON_MAGIC:
        s: str = body.decode("utf-8")
        return json.loads(s, object_hook=_bytes_json_object_hook)

    if magic == _PICKLE_MAGIC:
        return pickle.loads(body)

    return pickle.loads(payload)


def pack_args(args: Tuple[Any, ...]) -> bytes:
    return _try_json_dumps(list(args))


def pack_kwargs(kwargs: Dict[str, Any]) -> bytes:
    return _try_json_dumps(kwargs)


def unpack_args(payload: bytes) -> Tuple[Any, ...]:
    obj = _loads(payload)
    if obj is None:
        return tuple()
    if isinstance(obj, list):
        return tuple(obj)
    raise TypeError("args は list として復元される必要があります。")


def unpack_kwargs(payload: bytes) -> Dict[str, Any]:
    obj = _loads(payload)
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    raise TypeError("kwargs は dict として復元される必要があります。")


def pack_result(result: Any) -> bytes:
    return _try_json_dumps(result)


def unpack_result(payload: bytes) -> Any:
    return _loads(payload)
