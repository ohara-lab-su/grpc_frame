#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Kengo NAKADA
kengo.nakada@mat.shimane-u.ac.jp
kengo.nakada@gmail.com
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Union, Tuple, Callable, Sequence

import grpc

import grpc_frame.adapter as adapter
import grpc_frame.ctrl_pb2 as ctrl_pb2


class GrpcClient:
    """
    gRPC Control サービスに対する汎用クライアントクラス。

    このクラスは ctrl.Control サービスに接続し、
    サーバー側で公開されている制御メソッドを Describe RPC により取得し、
    各メソッドを Python メソッドとして動的にバインドする。

    設計上の特徴:
    - gRPC の low-level API（unary_unary）を直接使用する
    - protobuf の Stub クラスには依存しない
    - サーバー側のメソッド追加・削除に対してクライアント側のコード変更を不要とする
    - adapter を用いて引数・戻り値の表現形式を統一する

    Attributes:
        _channel:
            gRPC サーバーとの通信に使用する Channel
        _rpc_describe:
            ctrl.Control/Describe RPC 呼び出し関数
        _rpc_call:
            ctrl.Control/Call RPC 呼び出し関数
        _method_table:
            サーバー側メソッド名とシグネチャの対応表
        _logger:
            クライアント動作記録用ロガー
        _timeout_sec:
            RPC 呼び出し時のタイムアウト秒数
    """

    def __init__(
        self,
        server_ip: str,
        server_port: int,
        logger: Optional[Any] = None,
        log_level: str = "INFO",
        timeout_sec: Optional[float] = None,
    ) -> None:
        """
        GrpcClient を初期化する。

        指定されたサーバーアドレスに対して gRPC Channel を生成し、
        Describe RPC を用いてサーバー側の公開メソッド一覧を取得する。
        取得した各メソッドは動的に Python メソッドとして self にバインドされる。

        Args:
            server_ip:
                gRPC サーバーの IP アドレス
            server_port:
                gRPC サーバーのポート番号
            logger:
                ログ出力用オブジェクト。
                None の場合は標準 logging を使用する。
            log_level:
                logger 未指定時に使用するログレベル
            timeout_sec:
                RPC 呼び出し時のタイムアウト秒数。
                None の場合は gRPC のデフォルト挙動に従う。
        """
        if logger is None:
            import logging

            logging.basicConfig(level=log_level.upper())
            logger = logging.getLogger(__name__)

        self._logger: Optional[Any] = logger
        self._timeout_sec: Optional[float] = timeout_sec

        addr: str = f"{server_ip}:{server_port}"

        self._logger.info(f"[GrpcClient] connect to {addr}")

        # 非 TLS の gRPC チャネルを生成
        self._channel: grpc.Channel = grpc.insecure_channel(addr)

        # Describe RPC（メソッド一覧取得）を low-level API で定義
        self._rpc_describe = self._channel.unary_unary(
            "/ctrl.Control/Describe",
            request_serializer=ctrl_pb2.Empty.SerializeToString,
            response_deserializer=ctrl_pb2.MethodTable.FromString,
        )

        # Call RPC（汎用メソッド呼び出し）を low-level API で定義
        self._rpc_call = self._channel.unary_unary(
            "/ctrl.Control/Call",
            request_serializer=ctrl_pb2.DispatchRequest.SerializeToString,
            response_deserializer=ctrl_pb2.DispatchResponse.FromString,
        )

        # サーバー側メソッド名とシグネチャの対応表
        self._method_table: Dict[str, str] = {}

        # サーバーからメソッド一覧を取得し、動的にバインド
        self._bind_remote_methods()

    def is_connected(self) -> bool:
        """
        gRPC サーバーとの接続可否を確認する。

        Describe RPC を実行できるかどうかをもって、
        サーバーが到達可能かつ応答可能であるかを判定する。

        Returns:
            bool:
                Describe RPC が成功した場合 True、
                例外が発生した場合 False
        """
        try:
            # self._logger.debug("[GrpcClient] check connection")

            # Describe RPC が成功するかで接続可否を判定
            _ = self._rpc_describe(
                ctrl_pb2.Empty(),
                timeout=self._timeout_sec,
            )
            return True

        except Exception:
            return False

    def _bind_remote_methods(self) -> None:
        """
        サーバー側の公開メソッドを取得し、動的にバインドする。

        Describe RPC を用いてサーバー側の MethodTable を取得し、
        各メソッドについて dispatcher 関数を生成して self に属性として追加する。

        この処理により、
        クライアント側からは通常の Python メソッド呼び出しとして
        RPC を透過的に利用できるようになる。
        """
        self._logger.info("[GrpcClient] Describe request")

        # サーバーから公開メソッド一覧を取得
        table = self._rpc_describe(
            ctrl_pb2.Empty(),
            timeout=self._timeout_sec,
        )

        # 各メソッドについて dispatcher を生成し self に動的追加
        for m in table.methods:
            name: str = str(m.name)
            sig: str = str(m.signature)

            # メソッド名とシグネチャを内部表に保存
            self._method_table[name] = sig

            self._logger.info(f"[GrpcClient] bind method: {name} {sig}")

            # method_name 固定の dispatcher 関数を生成
            dispatcher = self._make_dispatcher(method_name=name)

            # self.<method_name> として動的に属性追加
            setattr(self, name, dispatcher)

        self._logger.info("[GrpcClient] method binding completed")

    def _make_dispatcher(
        self,
        *,
        method_name: str,
    ) -> Callable[..., Any]:
        """
        指定されたメソッド名に対応する RPC 呼び出し関数を生成する。

        生成される関数は以下の処理を行う:
        - Python の *args / **kwargs を adapter によりシリアライズ
        - ctrl.Control/Call RPC を実行
        - 戻り値をデシリアライズして返却
        - サーバー側エラー時は RuntimeError を送出

        Args:
            method_name:
                サーバー側で公開されているメソッド名

        Returns:
            Callable[..., Any]:
                RPC 呼び出しを行う関数
        """

        # サーバー側 1 メソッドに対応するローカル関数を生成
        def _method(
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            self._logger.info(
                f"[GrpcClient][{method_name}] call args={args} kwargs={kwargs}"
            )

            # Python 引数を RPC 用にシリアライズ
            args_bin: bytes = adapter.pack_args(tuple(args))
            kwargs_bin: bytes = adapter.pack_kwargs(kwargs)

            # DispatchRequest を構築
            req = ctrl_pb2.DispatchRequest(
                method=method_name,
                args=args_bin,
                kwargs=kwargs_bin,
            )

            # Call RPC を実行
            resp = self._rpc_call(req, timeout=self._timeout_sec)

            ok: bool = bool(resp.ok)
            if ok:
                self._logger.info(f"[GrpcClient][{method_name}] completed")
                # 戻り値をデシリアライズして返却
                return adapter.unpack_result(resp.result)

            err: str = str(resp.error)
            self._logger.info(f"[GrpcClient][{method_name}] failed: {err}")
            raise RuntimeError(err)

        # 動的に生成した関数名を RPC メソッド名に合わせる
        _method.__name__ = method_name
        return _method

    def close(self) -> None:
        """
        gRPC Channel をクローズする。

        クライアント終了時に呼び出されることを想定しており、
        通信リソースを明示的に解放する。
        """
        self._logger.info("[GrpcClient] close channel")
        try:
            self._channel.close()
        except Exception:
            pass
