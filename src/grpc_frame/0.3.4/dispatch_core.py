#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Kengo NAKADA
kengo.nakada@mat.shimane-u.ac.jp
kengo.nakada@gmail.com
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Union, Tuple, Callable, Sequence

import inspect
from dataclasses import dataclass


@dataclass(frozen=True)
class MethodInfo:
    name: str
    signature: str


def list_public_methods(
    ctrl_obj: Any,
) -> List[MethodInfo]:
    """
    dispatch_core.list_public_methods() は
    inspect.getmembers() で列挙し、
    名前が _ で始まるものは除外
    callable() でないものも除外

    「RPC として見せたい API」は ctrl 側で public メソッドにするのが唯一の入口

    Args:
        ctrl_obj:

    Returns:

    """
    # 収集したメソッド情報を格納するリスト
    methods: List[MethodInfo] = []

    # ctrl_obj が持つ全メンバー（属性・メソッド）を列挙
    for name, member in inspect.getmembers(ctrl_obj):
        # "_" で始まる名前は非公開扱いとして除外
        if name.startswith("_"):
            continue

        # callable でないもの（属性・定数など）は除外
        is_callable: bool = callable(member)
        if not is_callable:
            continue

        # メソッドのシグネチャを取得
        sig: str = ""
        try:
            # inspect.signature により引数情報を文字列化
            sig = str(inspect.signature(member))
        except Exception:
            sig = "()"

        # メソッド名とシグネチャを MethodInfo として記録
        methods.append(MethodInfo(name=name, signature=sig))

    # メソッド名でソートして順序を安定化
    methods.sort(key=lambda m: m.name)

    # 公開メソッド一覧
    return methods
