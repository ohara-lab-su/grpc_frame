#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, List


@dataclass(frozen=True)
class MethodInfo:
    name: str
    signature: str


def list_public_methods(ctrl_obj: Any) -> List[MethodInfo]:
    methods: List[MethodInfo] = []

    for name, member in inspect.getmembers(ctrl_obj):
        if name.startswith("_"):
            continue

        is_callable: bool = callable(member)
        if not is_callable:
            continue

        sig: str = ""
        try:
            sig = str(inspect.signature(member))
        except Exception:
            sig = "()"

        methods.append(MethodInfo(name=name, signature=sig))

    methods.sort(key=lambda m: m.name)
    return methods
