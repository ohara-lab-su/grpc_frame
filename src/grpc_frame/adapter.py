#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple


def pack_args(args: Tuple[Any, ...]) -> bytes:
    data: List[Any] = list(args)
    text: str = json.dumps(data, ensure_ascii=False)
    return text.encode("utf-8")


def pack_kwargs(kwargs: Dict[str, Any]) -> bytes:
    text: str = json.dumps(kwargs, ensure_ascii=False)
    return text.encode("utf-8")


def unpack_args(data: bytes) -> Tuple[Any, ...]:
    if data is None:
        return tuple()

    if len(data) == 0:
        return tuple()

    text: str = data.decode("utf-8")
    obj: Any = json.loads(text)

    if isinstance(obj, list):
        return tuple(obj)

    raise TypeError("args_json must decode to list")


def unpack_kwargs(data: bytes) -> Dict[str, Any]:
    if data is None:
        return {}

    if len(data) == 0:
        return {}

    text: str = data.decode("utf-8")
    obj: Any = json.loads(text)

    if isinstance(obj, dict):
        return obj

    raise TypeError("kwargs_json must decode to dict")


def pack_result(obj: Any) -> bytes:
    text: str = json.dumps(obj, ensure_ascii=False)
    return text.encode("utf-8")


def unpack_result(data: bytes) -> Any:
    if data is None:
        return None

    if len(data) == 0:
        return None

    text: str = data.decode("utf-8")
    return json.loads(text)
