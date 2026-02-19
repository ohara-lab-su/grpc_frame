#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kengo NAKADA
kengo.nakada@mat.shimane-u.ac.jp
kengo.nakada@gmail.com

gRPC サーバー実装（動的ディスパッチ + Event ストリーミング）

- _ControlServicer: ctrl_obj の public メソッドを動的に RPC 化
- _EventsServicer: EventBus のイベントを gRPC でストリーム配信
- create_grpc_server: 上記サービスを束ねた grpc.Server を生成

"""

from __future__ import annotations

import traceback

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


def _format_exception(e: BaseException) -> str:
    """例外を型名とスタックトレース込みの文字列に整形する。

    Args:
        e: 捕捉した例外である。

    Returns:
        型名・メッセージ・スタックトレースを連結した文字列である。
    """
    exc_type = type(e)
    tb = e.__traceback__
    return "".join(traceback.format_exception(exc_type, e, tb))


class _ControlServicer(
    ctrl_pb2_grpc.ControlServicer,
):
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
        event_bus: Optional[EventBus] = None,
        logger: Optional[Any] = None,
        log_level: Optional[str] = None,
    ) -> None:
        """
        ControlServicer を初期化する。

        Args:
            ctrl_obj:
                RPC 経由で操作対象となる制御オブジェクト。
                public メソッドのみが RPC として公開される。
            event_bus: イベントよう(Noneならばイベントを使わない)
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
        context: grpc.ServicerContext,
    ) -> ctrl_pb2.DispatchResponse:
        """"""
        # request.method は ctrl_obj の public メソッド名
        method_name: str = str(request.method)

        self._logger.info(f"[Frame:ControlServicer][{method_name}] called")

        # ディスパッチするべきメソッドを見つける
        try:
            # 動的に対象メソッドを解決する（存在しなければ例外）
            target = getattr(self._ctrl_obj, method_name)
        except Exception as e:
            self._logger.error(
                f"[Frame:ControlServicer][{method_name}] getattr failed: {e}"
            )

            return ctrl_pb2.DispatchResponse(
                ok=False,
                result=b"",
                # error=str(e),
                error=_format_exception(e),
            )

        # 実際にメソッドを実行する
        try:
            # protobuf から引数を復元
            args = adapter.unpack_args(request.args)
            kwargs = adapter.unpack_kwargs(request.kwargs)

            self._logger.info(
                f"[Frame:ControlServicer][{method_name}] args={args} kwargs={kwargs}"
            )

            # 実メソッドを実行
            result = target(*args, **kwargs)

            # 戻り値を protobuf 用にシリアライズ
            result_bin: bytes = adapter.pack_result(result)

            self._logger.info(f"[Frame:ControlServicer][{method_name}] completed")

            return ctrl_pb2.DispatchResponse(
                ok=True,
                result=result_bin,
                error="",
            )

        except Exception as e:
            self._logger.error(f"[Frame:ControlServicer][{method_name}] failed: {e}")

            return ctrl_pb2.DispatchResponse(
                ok=False,
                result=b"",
                # error=str(e),
                error=_format_exception(e),
            )


class _EventsServicer(
    events_pb2_grpc.EventsServicer,
):
    """
    EventBus のイベントを gRPC ストリームで配信するサービス実装。

    Subscribe は EventBus の generator をそのまま gRPC の
    server-side streaming として返す。
    """

    def __init__(
        self,
        *,
        event_bus: EventBus,
        logger: Optional[Any] = None,
        log_level: Optional[str] = None,
    ) -> None:
        """
        Args:
            event_bus: EventBus インスタンス（イベント配信元）
            logger: ロガー（未指定でも動作に影響しない）
            log_level: ログレベル
        """

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
        """
        EventBus の publish を gRPC streaming として転送する。

        Args:
            request: topic / once / source を含む SubscribeRequest
            context: gRPC コンテキスト

        Yields:
            events_pb2.Event: 受信イベント
        """
        topic: str = request.topic
        once: bool = bool(request.once)
        source: str = str(request.source)

        for item in self._bus.subscribe(topic=topic, once=once, source=source):
            event = events_pb2.Event()
            event.topic = item.topic
            event.payload = adapter.pack_result(item.payload_obj)
            event.ts_ns = item.ts_ns
            event.source = item.source
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

    Args:
        ctrl_obj: Control サービスのディスパッチ対象（public メソッドのみ公開）
        max_workers: gRPC の ThreadPoolExecutor の worker 数
        event_bus: EventBus（None の場合は内部生成）
        logger: ロガー
        log_level: ログレベル

    Returns:
        grpc.Server: gRPC サーバーインスタンス
    """
    if logger is None:
        import logging

        log_level = log_level or "INFO"
        logging.basicConfig(level=log_level.upper())
        logger = logging.getLogger(__name__)

    # EventBus が未指定なら内部で生成する
    if event_bus is None:
        # Event がない時(default EventBus作成)
        event_bus = EventBus()

    # gRPC サーバー本体（ThreadPoolExecutor）
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

    # gRPC サーバー本体（ThreadPoolExecutor）
    ctrl_pb2_grpc.add_ControlServicer_to_server(
        ctrl_servicer,
        server,
    )

    events_servicer = _EventsServicer(
        event_bus=event_bus,
        logger=logger,
        log_level=log_level,
    )

    # Events サービスを登録
    events_pb2_grpc.add_EventsServicer_to_server(
        events_servicer,
        server,
    )

    return server
