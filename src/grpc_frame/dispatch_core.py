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
    """公開対象メソッドのメタ情報を保持するデータクラスである。

    Attributes:
        name: メソッド名である。
        signature: 署名文字列である。取得できない場合は "()" とする。
    """

    name: str
    signature: str


def list_public_methods(
    ctrl_obj: Any,
) -> List[MethodInfo]:
    """制御オブジェクトの public callable を列挙して MethodInfo の配列を返す関数である。

    本関数は gRPC の Describe 用途を想定し、公開対象を「呼び出し可能な public メンバー」に限定する。
    ここで property は列挙時に評価され得るため、静的取得で判定し、列挙対象から除外する。

    Args:
        ctrl_obj: 対象の制御オブジェクトである。

    Returns:
        List[MethodInfo]:
            public callable の (name, signature) 一覧である。name 昇順にソートして返す。
    """
    # 収集したメソッド情報を格納するリスト
    methods: List[MethodInfo] = []

    # # BEFORE（旧版の要点：getmembers による列挙）
    # for name, member in inspect.getmembers(ctrl_obj):
    #     if name.startswith("_"):
    #         continue

    #     if not callable(member):
    #         continue

    #     signature = str(inspect.signature(member))
    #     methods.append(MethodInfo(name=name, signature=signature))

    # 新版
    # inspect.getmembers(ctrl_obj) は property を評価し得るため使用しない
    # dir() により名前一覧のみを取得し、値の評価を伴う走査を避ける
    for name in dir(ctrl_obj):
        # public 以外は除外する
        if name.startswith("_"):
            continue

        # getattr_static() で descriptor を評価せずに取得する
        try:
            static_member = inspect.getattr_static(ctrl_obj, name)
        except Exception:
            # 取得不能な名前は列挙対象から外す設計
            continue

        # property は評価時に副作用（COM 呼び出し等）を生む可能性があるため除外する
        # staticmethod/classmethod/callable のみを候補として扱う
        if isinstance(static_member, property):
            continue

        is_candidate: bool = False

        if isinstance(static_member, staticmethod):
            is_candidate = True
        elif isinstance(static_member, classmethod):
            is_candidate = True
        else:
            if callable(static_member):
                is_candidate = True

        if not is_candidate:
            continue

        # 実体を取得し、呼び出し可能であることを確認する
        try:
            member = getattr(ctrl_obj, name)
        except Exception:
            # 実体取得で例外が出るものは列挙対象から外す
            continue

        if not callable(member):
            continue

        # callable の引数の形を表す情報、署名
        # 署名を文字列化する。取得不能なら "()" に丸める。
        sig: str = ""
        try:
            sig = str(inspect.signature(member))
        except Exception:
            sig = "()"

        methods.append(MethodInfo(name=name, signature=sig))

    # name 昇順にそろえて返す
    methods.sort(key=lambda m: m.name)
    return methods
