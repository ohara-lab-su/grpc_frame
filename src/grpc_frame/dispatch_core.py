#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations
from typing import Any, Dict, List, Optional, Union, Tuple, Callable, Sequence

import inspect
from dataclasses import dataclass


@dataclass(frozen=True)
class MethodInfo:
    name: str
    signature: str


def list_public_methods(ctrl_obj: Any) -> List[MethodInfo]:
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
