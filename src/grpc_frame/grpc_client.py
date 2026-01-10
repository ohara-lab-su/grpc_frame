# grpc_frame/grpc_client.py
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple, Type
import importlib
import inspect

import grpc
from google.protobuf import empty_pb2


import grpc_frame.dispatch_core as core
from x_logger import XLogger

_logger = XLogger(log_level="debug", logger_name="grpc_client",)


def _normalize_method_path(
    method_path: Any,
) -> str:
    """
    gRPC の method path を文字列として正規化する。

    - bytes の場合は decode を試みる
    - str の場合はそのまま返す
    - それ以外は str() による文字列化を行う

    Args:
        method_path: gRPC 内部で保持される method path

    Returns:
        str: 正規化された method path
    """
    _logger.debug(f"[DEBUG] _normalize_method_path: {method_path}")

    if isinstance(method_path, bytes):
        try:
            return method_path.decode("utf-8")
        except Exception:
            return method_path.decode("latin-1", errors="replace")

    if isinstance(method_path, str):
        return method_path

    return str(method_path)


def _parse_rpc_name_from_method_path(
    method_path: Any,
) -> str:
    """
    gRPC method path から RPC 名を抽出する。

    想定形式:
        /<package>.<Service>/<RpcName>

    最後の '/' 以降を RPC 名として取り出す。

    Args:
        method_path: gRPC method path (bytes / str)

    Returns:
        str: RPC 名

    Raises:
        ValueError: path 形式が不正、または RPC 名が空の場合
    """
    _logger.debug(f"[DEBUG] _parse_rpc_name_from_method_path: {method_path}")

    path: str = _normalize_method_path(method_path)
    parts: list[str] = path.split("/")
    if len(parts) < 2:
        raise ValueError(f"unexpected rpc method path: {path}")

    rpc_name: str = parts[-1]
    if rpc_name == "":
        raise ValueError(f"empty rpc name: {path}")

    return rpc_name


def _stub_module_to_pb2_module(
    stub_module_name: str,
) -> str:
    """
    stub モジュール名 (*_pb2_grpc) から pb2 モジュール名を導出する。

    例:
        xxx_pb2_grpc -> xxx_pb2

    Args:
        stub_module_name (str): stub クラスの __module__ 名

    Returns:
        str: 対応する pb2 モジュール名

    Raises:
        RuntimeError: モジュール名が想定形式でない場合
    """
    _logger.debug(f"[DEBUG] _stub_module_to_pb2_module: {stub_module_name}")

    if not stub_module_name.endswith("_pb2_grpc"):
        raise RuntimeError(
            f"stub module does not look like *_pb2_grpc: {stub_module_name}"
        )

    prefix: str = stub_module_name[: -len("_grpc")]
    return prefix


def _get_owner_from_serializer(
    serializer: Any,
) -> Optional[type]:
    """
    serializer / deserializer 関数から所有クラスを取得する。

    grpc が内部に保持する serializer が
    クラスメソッド由来の場合、その所有クラスを返す。

    Args:
        serializer: rpc が保持する serializer / deserializer

    Returns:
        Optional[type]: Message クラス、取得できない場合は None
    """
    _logger.debug(f"[DEBUG] _get_owner_from_serializer: {serializer}")

    owner: Any = getattr(serializer, "__self__", None)
    if owner is None:
        return None

    is_class: bool = inspect.isclass(owner)
    if not is_class:
        return None

    return owner


def _is_protobuf_base_message_class(
    cls: Type[Any],
) -> bool:
    """
    protobuf の基底 Message クラスそのものかどうかを判定する。

    google._upb._message.Message を基底クラスとする
    「抽象的な Message クラス」を除外する目的で用いる。

    Args:
        cls (Type[Any]): 判定対象クラス

    Returns:
        bool: protobuf の基底 Message クラスであれば True
    """
    _logger.debug(f"[DEBUG] _is_protobuf_base_message_class: {cls}")

    module_name: str = getattr(cls, "__module__", "")
    class_name: str = getattr(cls, "__name__", "")
    if module_name != "google._upb._message":
        return False
    if class_name != "Message":
        return False
    return True


# ----------------------------
# 以下クラス中で呼ばれる
# ----------------------------


def _resolve_request_class_from_rpc(
    rpc: Any,
    *,
    stub_class: Type[Any],
    logger: XLogger,
) -> Type[Any]:
    """
    rpc オブジェクトから Request Message クラスを解決する。

    解決順序:
    1. rpc._request_deserializer の owner
    2. rpc._request_serializer の owner
    3. rpc._method から RPC 名を解析し <RpcName>Request を探索
    4. 見つからない場合は Empty を使用

    Args:
        rpc: stub が保持する rpc callable
        stub_class: 使用中の stub クラス
        logger: ロガー

    Returns:
        Type[Any]: Request Message クラス
    """
    logger.debug(f"[DEBUG] _resolve_request_class_from_rpc: {rpc}")

    request_deserializer: Any = getattr(rpc, "_request_deserializer", None)
    if request_deserializer is not None:
        owner = _get_owner_from_serializer(request_deserializer)
        if owner is not None:
            is_base: bool = _is_protobuf_base_message_class(owner)
            if not is_base:
                return owner

    request_serializer: Any = getattr(rpc, "_request_serializer", None)
    if request_serializer is not None:
        owner2 = _get_owner_from_serializer(request_serializer)
        if owner2 is not None:
            is_base2: bool = _is_protobuf_base_message_class(owner2)
            if not is_base2:
                return owner2

    method_path: Any = getattr(rpc, "_method", None)
    if method_path is None:
        logger.debug("[GrpcClient] rpc has no _method; fallback Empty")
        return empty_pb2.Empty

    rpc_name: str = _parse_rpc_name_from_method_path(method_path)
    request_name: str = f"{rpc_name}Request"

    stub_module_name: str = getattr(stub_class, "__module__", "")
    if stub_module_name == "":
        raise RuntimeError("stub_class has no __module__")

    pb2_module_name: str = _stub_module_to_pb2_module(stub_module_name)

    logger.debug(
        f"[GrpcClient] resolve request: rpc_name={rpc_name}, pb2_module={pb2_module_name}"
    )

    pb2_module = importlib.import_module(pb2_module_name)

    has_req: bool = hasattr(pb2_module, request_name)
    if has_req:
        return getattr(pb2_module, request_name)

    logger.debug(
        f"[GrpcClient] request message not found: {pb2_module_name}.{request_name} -> fallback Empty"
    )
    return empty_pb2.Empty


def build_request_message(
    request_cls: Type[Any],
    kwargs: Dict[str, Any],
) -> Any:
    """
    Request Message インスタンスを生成し、kwargs から内容を埋める。

    - constructor は使用しない
    - 常に descriptor-driven な fill_message を用いる
    - kwargs は ctrl メソッド引数から生成される dict を想定

    Args:
        request_cls (Type[Any]): Request Message クラス
        kwargs (Dict[str, Any]): フィールド名 -> 値

    Returns:
        Any: 構築済み Request Message
    """
    _logger.debug(f"[DEBUG][build_request_message] BEGIN")
    _logger.debug(f"  request_cls =", request_cls)
    _logger.debug(f"  input kwargs =", kwargs)

    # # --- 重要: まず constructor 経由を試し、成功しても「何がセットされたか」を必ず記録 ---
    # try:
    #     _logger.debug("[DEBUG][build_request_message] try: calling constructor")
    #     return request_cls(**kwargs)
    # except Exception as e:
    #     _logger.debug("[DEBUG][build_request_message] constructor FAILED:", e)

    # req: Any = request_cls()
    # _logger.debug(
    #     "[DEBUG][build_request_message] fallback: empty request created =", req
    # )

    # core.fill_message(req, kwargs)

    # constructor 経由は使わず、常に descriptor-driven で埋める
    req: Any = request_cls()
    _logger.debug("[DEBUG][build_request_message] empty request created =", req)

    core.fill_message(req, kwargs)

    _logger.debug("[DEBUG][build_request_message] after fill_message =", req)
    _logger.debug("[DEBUG][build_request_message] END")
    return req


class GrpcClient:
    """
    ctrl クラスと gRPC stub を動的にバインドする汎用 gRPC クライアント基底クラス。

    責務:
    - ctrl クラスの public メソッドを走査
    - 対応する RPC が存在する場合に dispatcher を動的生成
    - Python 呼び出しを gRPC Request/Response に変換

    派生クラスは以下を定義する:
    - _ctrl_class
    - _stub_class
    - _client_log_title
    """

    _ctrl_class: type
    _stub_class: type
    _client_log_title: str

    def __init__(
        self,
        server_ip: str,
        server_port: int,
        logger: Optional[XLogger] = None,
    ) -> None:
        """
        gRPC チャンネルと stub を生成し、ctrl メソッドをバインドする。

        Args:
            server_ip (str): gRPC サーバの IP アドレス
            server_port (int): gRPC サーバのポート番号
            logger (Optional[XLogger]): 使用するロガー
        """
        self._logger: XLogger = logger or XLogger()

        addr: str = f"{server_ip}:{server_port}"
        self._channel: grpc.Channel = grpc.insecure_channel(addr)
        self._stub: Any = self._stub_class(self._channel)

        self._logger.info(f"== Create {self._client_log_title}")
        self._logger.info(f" gRPC server = {server_ip}:{server_port}")

        self._logger.info("bind_ctrl_method")
        self._bind_ctrl_methods()

    def is_connected(
        self,
        timeout: float = 0.5,
    ) -> bool:
        """
        gRPC チャンネルが接続可能状態かどうかを確認する。

        Args:
            timeout (float): 接続待ちタイムアウト秒

        Returns:
            bool: 接続可能であれば True
        """
        try:
            grpc.channel_ready_future(self._channel).result(timeout=timeout)
            return True
        except Exception:
            return False

    def _bind_ctrl_methods(self) -> None:
        """
        ctrl クラスのメソッドを走査し、RPC が存在するものをバインドする。

        - ctrl_method -> RpcName の名前変換を行う
        - stub に該当 RPC が存在しない場合は無視する

        Returns:
            None
        """
        for name, method in inspect.getmembers(self._ctrl_class, inspect.isfunction):
            if name.startswith("_"):
                continue

            rpc_name: str = core.ctrl_method_to_rpc_name(name)
            has_rpc: bool = hasattr(self._stub, rpc_name)

            self._logger.info(
                f"[GrpcClient] scan ctrl method: {name} -> {rpc_name}, has_rpc={has_rpc}"
            )

            if not has_rpc:
                continue

            rpc: Any = getattr(self._stub, rpc_name)
            sig: inspect.Signature = inspect.signature(method)

            dispatcher = self._make_dispatcher(
                method_name=name,
                rpc_name=rpc_name,
                sig=sig,
                rpc=rpc,
            )
            setattr(self, name, dispatcher)

    def _make_dispatcher(
        self,
        *,
        method_name: str,
        rpc_name: str,
        sig: inspect.Signature,
        rpc: Any,
    ) -> Callable[..., Any]:
        """
        ctrl メソッド呼び出しを gRPC RPC 呼び出しに変換する dispatcher を生成する。

        dispatcher の責務:
        - Python 引数を Signature に基づいて正規化
        - Request Message を構築
        - RPC を実行
        - Response を unwrap して返す

        Args:
            method_name (str): ctrl 側メソッド名
            rpc_name (str): RPC 名
            sig (inspect.Signature): ctrl メソッドのシグネチャ
            rpc: stub が保持する RPC callable

        Returns:
            Callable[..., Any]: dispatcher 関数
        """
        request_cls = _resolve_request_class_from_rpc(
            rpc,
            stub_class=self._stub_class,
            logger=self._logger,
        )

        self._logger.info(
            f"[GrpcClient] dispatcher created: {method_name} -> {rpc_name} "
            f"(request_cls={request_cls}, module={getattr(request_cls, '__module__', '')})"
        )

        def _method(*args: Any, **kwargs: Any) -> Any:
            self._logger.info(f"[GrpcClient] CALL {method_name}() begin")
            self._logger.info(f"[GrpcClient] args={args}, kwargs={kwargs}")

            try:
                bound = sig.bind_partial(None, *args, **kwargs)
                bound.apply_defaults()

                # req_kwargs: Dict[str, Any] = {}
                # for k, v in bound.arguments.items():
                #     if k == "self":
                #         continue
                #     req_kwargs[k] = v

                # self._logger.debug(f"[GrpcClient] req_kwargs={req_kwargs}")

                # request = build_request_message(request_cls, req_kwargs)

                # self._logger.debug(f"[GrpcClient][DEBUG] request content = {request}")
                # self._logger.debug(
                #     f"[GrpcClient] request built: type={type(request)}, module={type(request).__module__}"
                # )

                # self._logger.debug("[GrpcClient] rpc call start")
                # resp = rpc(request)
                # self._logger.debug("[GrpcClient] rpc call done")

                ordered_args: List[Any] = []
                ordered_kwargs: Dict[str, Any] = {}

                for name, value in bound.arguments.items():
                    if name == "self":
                        continue
                    if name in kwargs:
                        ordered_kwargs[name] = value
                    else:
                        ordered_args.append(value)

                # request 構築は proto descriptor のみで決定
                self._logger.debug("[GrpcClient] rpc call start")
                request = request_cls()
                core.fill_message(request, ordered_args + list(ordered_kwargs.values()))

                resp = rpc(request)

                return core.unwrap_response(resp)

            except Exception as e:
                self._logger.error(
                    f"[{self.__class__.__name__}] {method_name} failed: {e}"
                )
                return False

        _method.__name__ = method_name
        _method.__signature__ = sig
        return _method
