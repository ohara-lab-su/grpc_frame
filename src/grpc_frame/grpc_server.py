#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Kengo NAKADA
kengo.nakada@mat.shimane-u.ac.jp
kengo.nakada@gmail.com
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Union, Tuple, Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

import threading
import grpc

import grpc_frame.adapter as adapter
import grpc_frame.dispatch_core as dispatch_core

# ctrl
import grpc_frame.ctrl_pb2 as ctrl_pb2
import grpc_frame.ctrl_pb2_grpc as ctrl_pb2_grpc

# events
import grpc_frame.events_pb2 as events_pb2
import grpc_frame.events_pb2_grpc as events_pb2_grpc
import grpc_frame.event_bus as event_bus


class _ControlServicer(ctrl_pb2_grpc.ControlServicer):
    """
    gRPC Control サービスのサーバー側実装クラス。

    このクラスは gRPC で定義された ctrl.Control サービスを実装し、
    任意の制御オブジェクト（ctrl_obj）の public メソッドを
    動的に RPC として公開する。

    method_name = request.method で
     getattr(self._ctrl_obj, method_name) を取り、
     adapter.unpack_args/kwargs してそのまま呼んで返す
    つまり RPC は ctrl_obj の Python 実装そのもので決まる

    役割:
    - Describe RPC:
        ctrl_obj が持つ public メソッド一覧とそのシグネチャを返す
    - Call RPC:
        クライアントから指定されたメソッド名を getattr により解決し、
        引数・戻り値をシリアライズして実行結果を返す

    設計上の特徴:
    - ctrl_obj の型や実装には依存しない
    - dispatch_core による introspection にのみ依存する
    - adapter により引数・戻り値の表現形式を統一する

    Attributes:
        _ctrl_obj:
            実際の制御対象オブジェクト
        _logger:
            任意のロガー（未指定の場合でも動作に影響しない）
    """

    def __init__(
        self,
        ctrl_obj: Any,
        logger: Optional[Any] = None,
        log_level: str = "INFO",
    ) -> None:
        """
        ControlServicer を初期化する。

        Args:
            ctrl_obj:
                RPC 経由で操作対象となる制御オブジェクト。
                public メソッドのみが RPC として公開される。
            logger:
                ログ出力用のオブジェクト。
                None の場合でもクラスの動作自体には影響しない。
        """
        # RPC 経由で操作される実体オブジェクトを保持
        self._ctrl_obj: Any = ctrl_obj

        if logger is None:
            import logging

            logging.basicConfig(level=log_level.upper())
            logger = logging.getLogger(__name__)

        self._logger: Optional[Any] = logger

        # proto で定義したイベントを呼ぶ仕組みをサーバー側に入れる
        try:
            set_event_bus = getattr(ctrl, "_set_event_bus")
        except AttributeError:
            set_event_bus = None

        if set_event_bus is not None and callable(set_event_bus):
            try:
                # set_event_bus が Callable であることを明示
                cast(Callable, set_event_bus)(_event_bus)
            except Exception:
                pass

    def Describe(
        self,
        request: ctrl_pb2.Empty,
        context: Any,
    ) -> ctrl_pb2.MethodTable:
        """
        制御オブジェクトの public メソッド一覧を返す RPC。

        ctrl_obj に対して dispatch_core.list_public_methods() を適用し、
        各メソッド名とシグネチャを MethodTable として返却する。

        この RPC はクライアント側で:
        - 利用可能な RPC メソッドの列挙
        - 動的メソッドバインド
        に使用される。

        Args:
            request:
                ctrl_pb2.Empty 型のリクエスト（内容は使用しない）
            context:
                gRPC のコンテキストオブジェクト

        Returns:
            ctrl_pb2.MethodTable:
                公開メソッド名とシグネチャの一覧
        """
        log_method: str = "Describe"

        self._logger.info(
            f"[Frame:ControlServicer][{log_method}] called",
        )

        # ctrl_obj が持つ public メソッドを introspection により取得
        infos = dispatch_core.list_public_methods(self._ctrl_obj)

        # protobuf の MethodTable を構築
        table = ctrl_pb2.MethodTable()
        for info in infos:
            mi = table.methods.add()
            mi.name = info.name
            mi.signature = info.signature

        self._logger.info(f"[Frame:ControlServicer][{log_method}] completed")

        return table

    def Call(
        self,
        request: ctrl_pb2.DispatchRequest,
        context: Any,
    ) -> ctrl_pb2.DispatchResponse:
        """
        指定されたメソッドを実行する RPC。

        request.method に含まれるメソッド名を ctrl_obj から getattr で取得し、
        adapter を用いて引数を復元した上で実行する。

        処理の流れ:
        1. メソッド名を文字列として取得
        2. ctrl_obj から対応する callable を取得
        3. args / kwargs をデシリアライズ
        4. メソッドを実行
        5. 戻り値をシリアライズして返却

        例外処理:
        - メソッド取得失敗時は ok=False と error を返す
        - 実行時例外も同様に ok=False として返却する

        Args:
            request:
                ctrl_pb2.DispatchRequest
                - method: 呼び出すメソッド名
                - args: シリアライズされた位置引数
                - kwargs: シリアライズされたキーワード引数
            context:
                gRPC のコンテキストオブジェクト

        Returns:
            ctrl_pb2.DispatchResponse:
                - ok: 実行成否
                - result: シリアライズされた戻り値
                - error: エラーメッセージ（失敗時）
        """
        method_name: str = str(request.method)

        self._logger.info(f"[Frame:ControlServicer][{method_name}] called")

        try:
            # ctrl_obj から対象メソッドを動的に取得
            target = getattr(self._ctrl_obj, method_name)
        except Exception as e:
            self._logger.error(
                f"[Frame:ControlServicer][{method_name}] getattr failed: {e}"
            )
            return ctrl_pb2.DispatchResponse(ok=False, result=b"", error=str(e))

        try:
            # シリアライズされた引数を Python オブジェクトに復元
            args = adapter.unpack_args(request.args)
            kwargs = adapter.unpack_kwargs(request.kwargs)

            self._logger.info(
                f"[Frame:ControlServicer][{method_name}] args={args} kwargs={kwargs}"
            )

            # 実メソッドを呼び出し
            result = target(*args, **kwargs)

            # 戻り値を RPC 用にシリアライズ
            result_bin: bytes = adapter.pack_result(result)

            self._logger.info(f"[Frame:ControlServicer][{method_name}] completed")

            return ctrl_pb2.DispatchResponse(ok=True, result=result_bin, error="")

        except Exception as e:
            self._logger.error(f"[Frame:ControlServicer][{method_name}] failed: {e}")
            return ctrl_pb2.DispatchResponse(ok=False, result=b"", error=str(e))


class _EventsServicer(events_pb2_grpc.EventsServicer):
    def __init__(self, bus: event_bus.EventBus) -> None:
        self._bus = bus

    def Subscribe(self, request, context):
        cancel = threading.Event()
        context.add_callback(cancel.set)

        for item in self._bus.subscribe(
            request.topic,
            once=request.once,
            cancel_event=cancel,
        ):
            yield events_pb2.Event(
                topic=item.topic,
                payload=adapter.pack_result(item.payload_obj),
                ts_ns=item.ts_ns,
                source=item.source,
            )


def create_grpc_server(
    ctrl_obj: Any,
    *,
    max_workers: int = 16,
    bus: Optional[event_bus.EventBus] = None,
):
    if bus is None:
        bus = event_bus.EventBus()

    server = grpc.server(ThreadPoolExecutor(max_workers=max_workers))

    ctrl_pb2_grpc.add_ControlServicer_to_server(
        _ControlServicer(ctrl_obj),
        server,
    )

    events_pb2_grpc.add_EventsServicer_to_server(
        _EventsServicer(bus),
        server,
    )

    return server, bus
