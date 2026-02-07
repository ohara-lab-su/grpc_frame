#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kengo NAKADA
kengo.nakada@mat.shimane-u.ac.jp
kengo.nakada@gmail.com
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

import grpc

from grpc_frame import adapter
from grpc_frame import ctrl_pb2
from grpc_frame import ctrl_pb2_grpc
from grpc_frame import dispatch_core
from grpc_frame import events_pb2
from grpc_frame import events_pb2_grpc
from grpc_frame.event_bus import EventBus


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
        *,
        ctrl_obj: Any,
        event_bus: Optional[EventBus],
        logger: Optional[Any] = None,
        log_level: Optional[str] = None,
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
        if logger is None:
            import logging

            log_level = log_level or "INFO"
            logging.basicConfig(level=log_level.upper())
            logger = logging.getLogger(__name__)

        self._logger: Optional[Any] = logger

        self._ctrl_obj = ctrl_obj
        self._event_bus = event_bus

        # ctrl 側がイベントバスを受け取れる実装を持つ場合のみ注入します。
        # ここは gRPC フレームの都合であり、ctrl の設計を強制しない
        setter = getattr(self._ctrl_obj, "_set_event_bus", None)
        if setter is not None:
            try:
                setter(self._event_bus)
            except Exception:
                # ctrl 側の実装事情で注入できないケースはあり得るため、ここでは握りつぶす
                pass

    def Describe(
        self,
        request: ctrl_pb2.Empty,
        context: grpc.ServicerContext,
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
        tbl = ctrl_pb2.MethodTable()
        for info in infos:
            row = tbl.rows.add()
            row.name = info.name
            row.signature = info.signature

        return tbl

    def Execute(
        self,
        request: ctrl_pb2.ExecuteRequest,
        context: grpc.ServicerContext,
    ) -> ctrl_pb2.ExecuteReply:
        """
        ctrl_obj の任意の public メソッドを実行する RPC。

        request.method で指定されたメソッド名を、request.args に入っている
        bytes ペイロードから adapter によりデコードして呼び出し、
        戻り値を bytes としてエンコードして返却する。

        Args:
            request:
                実行したいメソッド名と引数
            context:
                gRPC のコンテキスト

        Returns:
            ctrl_pb2.ExecuteReply:
                実行結果（bytes）
        """
        log_method: str = "Execute"

        self._logger.info(
            f"[Frame:ControlServicer][{log_method}] called method={request.method}",
        )

        method_name: str = request.method
        payload: bytes = request.args

        # args をデコード（dict を想定）
        data = adapter.decode_bytes(payload)
        if data is None:
            data = {}

        kwargs: dict[str, Any]
        if isinstance(data, dict):
            kwargs = data
        else:
            kwargs = {}

        # 動的ディスパッチ
        ret = dispatch_core.call_public_method(
            self._ctrl_obj,
            method_name,
            kwargs,
        )

        # 戻り値をエンコード
        out_b = adapter.encode_bytes(ret)

        reply = ctrl_pb2.ExecuteReply()
        reply.result = out_b
        return reply


class _EventsServicer(events_pb2_grpc.EventsServicer):
    """Events RPC service implementation."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        logger: Optional[Any] = None,
        log_level: Optional[str] = None,
    ) -> None:
        """"""
        if logger is None:
            import logging

            log_level = log_level or "INFO"
            logging.basicConfig(level=log_level.upper())
            logger = logging.getLogger(__name__)

        self._logger: Optional[Any] = logger
        self._bus = event_bus

    def Subscribe(
        self,
        request: events_pb2.SubscribeRequest,
        context: grpc.ServicerContext,
    ):
        topic: str = request.topic

        for payload in self._bus.subscribe(topic=topic):
            event = events_pb2.Event()
            event.topic = topic
            event.payload = adapter.encode_bytes(payload)
            yield event


def create_grpc_server(
    *,
    ctrl_obj: Any,
    max_workers: int = 10,
    event_bus: Optional[EventBus] = None,
    logger: Optional[Any] = None,
    log_level: Optional[str] = None,
) -> grpc.Server:
    """
    Control + Events の両サービスを載せた gRPC server を生成する。

    - ctrl_obj は Control サービスの動的ディスパッチ対象
    - event_bus が None の場合はフレーム側で EventBus を生成
    - ctrl_obj が _set_event_bus を持つ場合は注入される
    """
    if logger is None:
        import logging

        log_level = log_level or "INFO"
        logging.basicConfig(level=log_level.upper())
        logger = logging.getLogger(__name__)

    bus: EventBus
    if event_bus is None:
        # Event がない時(default EventBus作成)
        event_bus = EventBus()

    server = grpc.server(
        ThreadPoolExecutor(
            max_workers=max_workers,
        ),
    )

    ctrl_servicer = _ControlServicer(
        ctrl_obj=ctrl_obj,
        event_bus=event_bus,
        logger=logger,
        log_level=log_level,
    )

    ctrl_pb2_grpc.add_ControlServicer_to_server(
        ctrl_servicer,
        server,
    )

    events_servicer = _EventsServicer(
        event_bus=event_bus,
        logger=logger,
        log_level=log_level,
    )

    events_pb2_grpc.add_EventsServicer_to_server(
        events_servicer,
        server,
    )

    return server
