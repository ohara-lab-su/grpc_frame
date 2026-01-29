#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Kengo NAKADA
kengo.nakada@mat.shimane-u.ac.jp
kengo.nakada@gmail.com
"""


from __future__ import annotations
from typing import Any, Dict, List, Optional, Union, Tuple, Callable, Sequence

import base64
import json
import pickle

# JSON でシリアライズされたことを示す識別子（先頭 1 byte）
_JSON_MAGIC: bytes = b"J"

# pickle でシリアライズされたことを示す識別子（先頭 1 byte）
_PICKLE_MAGIC: bytes = b"P"


class _BytesJsonEncoder(json.JSONEncoder):
    # JSONEncoder を拡張し、bytes / bytearray を base64 文字列として扱う
    def default(
        self,
        obj: Any,
    ) -> Any:
        # bytes / bytearray は JSON で直接扱えないため base64 化
        if isinstance(obj, (bytes, bytearray)):
            b64: str = base64.b64encode(bytes(obj)).decode("ascii")
            # 復元用の識別キー "__bytes__" を付与
            return {"__bytes__": b64}

        # それ以外は標準の JSONEncoder に委譲
        return json.JSONEncoder.default(self, obj)


def _bytes_json_object_hook(d: Dict[str, Any]) -> Any:
    # JSON decode 時に "__bytes__" キーを検出した場合の復元処理
    if "__bytes__" in d:
        b64 = d["__bytes__"]
        if isinstance(b64, str):
            # base64 文字列を bytes に戻
            return base64.b64decode(b64.encode("ascii"))

    # 特殊形式でなければそのまま返す
    return d


def _try_json_dumps(obj: Any) -> bytes:
    try:
        # JSON によるシリアライズを最初に試みる
        s: str = json.dumps(
            obj,
            cls=_BytesJsonEncoder,  # bytes 対応エンコーダ
            ensure_ascii=False,  # Unicode をそのまま出力
            separators=(",", ":"),  # JSON を最小サイズにする
        )
        # JSON で成功した場合は識別子を先頭に付与
        return _JSON_MAGIC + s.encode("utf-8")
    except Exception:
        # JSON 化できないオブジェクトは pickle にフォールバック
        pass

    # pickle によるシリアライズ（最高プロトコル）
    payload: bytes = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)

    # pickle 識別子を先頭に付与
    return _PICKLE_MAGIC + payload


def _loads(payload: bytes) -> Any:
    # None はそのまま None として扱う
    if payload is None:
        return None

    # 空 payload も None とみなす
    if len(payload) == 0:
        return None

    # 先頭 1 byte を識別子として取得
    magic: bytes = payload[:1]
    body: bytes = payload[1:]

    # JSON フォーマットの場合
    if magic == _JSON_MAGIC:
        s: str = body.decode("utf-8")
        # bytes 復元用の object_hook を指定
        return json.loads(s, object_hook=_bytes_json_object_hook)

    # pickle フォーマットの場合
    if magic == _PICKLE_MAGIC:
        return pickle.loads(body)

    # 識別子が無い旧形式などは pickle として扱う
    return pickle.loads(payload)


def pack_args(
    args: Tuple[Any, ...],
) -> bytes:
    # 位置引数を list に変換してシリアライズ
    return _try_json_dumps(list(args))


def pack_kwargs(
    kwargs: Dict[str, Any],
) -> bytes:
    # キーワード引数を dict としてシリアライズ
    return _try_json_dumps(kwargs)


def unpack_args(payload: bytes) -> Tuple[Any, ...]:
    # シリアライズされた args を復元
    obj = _loads(payload)

    # None の場合は空タプル
    if obj is None:
        return tuple()

    # 正常系では list → tuple に変換
    if isinstance(obj, list):
        return tuple(obj)

    # 想定外の型はエラー
    raise TypeError("args は list として復元される必要があります。")


def unpack_kwargs(payload: bytes) -> Dict[str, Any]:
    # シリアライズされた kwargs を復元
    obj = _loads(payload)

    # None の場合は空 dict
    if obj is None:
        return {}

    # 正常系では dict をそのまま返す
    if isinstance(obj, dict):
        return obj
    raise TypeError("kwargs は dict として復元される必要があります。")


def pack_result(result: Any) -> bytes:
    # 戻り値をシリアライズ
    return _try_json_dumps(result)


def unpack_result(payload: bytes) -> Any:
    return _loads(payload)
