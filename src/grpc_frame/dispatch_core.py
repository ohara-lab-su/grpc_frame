#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Callable


def validate_method_name(method_name: str) -> None:
    if method_name is None:
        raise ValueError("method_name is None")

    if method_name == "":
        raise ValueError("method_name is empty")

    if method_name.startswith("_"):
        raise ValueError("private method is not allowed")


def resolve_ctrl_method(ctrl_obj: Any, method_name: str) -> Callable[..., Any]:
    validate_method_name(method_name)

    if ctrl_obj is None:
        raise ValueError("ctrl_obj is None")

    if not hasattr(ctrl_obj, method_name):
        raise AttributeError(f"ctrl has no method: {method_name}")

    fn: Any = getattr(ctrl_obj, method_name)

    if not callable(fn):
        raise TypeError(f"ctrl attribute is not callable: {method_name}")

    return fn
