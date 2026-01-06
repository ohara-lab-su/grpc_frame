#!/usr/bin/env python3
"""
K.NAKADA, kengo.nakada@mat.shimane-u.ac.jp, kengo.nakada@gmail.com

cobotta2.server_grpc.grpc_client

汎用 gRPC client（ctrl <-> client 対称モデル）
"""
from typing import Any, Callable, Dict, Optional, Type
import importlib
import inspect

import grpc
from google.protobuf import empty_pb2

from x_logger import XLogger


def _snake_to_camel(name: str) -> str:
    return "".join(word.capitalize() for word in name.split("_"))


def _to_rpc_name(method_name: str) -> str:
    """
    ctrl 側メソッド名 -> stub 側 RPC 名

    - snake_case は CamelCase に変換
    - moveP のように既に大文字を含む場合は、先頭だけ大文字化して残りは保持
    """
    if method_name == "":
        raise ValueError("empty method name")

    if "_" in method_name:
        return _snake_to_camel(method_name)

    head = method_name[0].upper()
    tail = method_name[1:]
    return f"{head}{tail}"


def _normalize_method_path(method_path: Any) -> str:
    if isinstance(method_path, bytes):
        try:
            return method_path.decode("utf-8")
        except Exception:
            return method_path.decode("latin-1", errors="replace")

    if isinstance(method_path, str):
        return method_path

    return str(method_path)


def _parse_rpc_name_from_method_path(method_path: Any) -> str:
    path = _normalize_method_path(method_path)
    parts = path.split("/")
    if len(parts) < 2:
        raise ValueError(f"unexpected rpc method path: {path}")

    rpc_name = parts[-1]
    if rpc_name == "":
        raise ValueError(f"empty rpc name: {path}")

    return rpc_name


def _get_bound_owner(obj: Any) -> Optional[type]:
    owner = getattr(obj, "__self__", None)
    if owner is None:
        return None
    if inspect.isclass(owner) is False:
        return None
    return owner


def _is_protobuf_base_message_class(cls: Type[Any]) -> bool:
    module_name = getattr(cls, "__module__", "")
    class_name = getattr(cls, "__name__", "")
    if module_name != "google._upb._message":
        return False
    if class_name != "Message":
        return False
    return True


def _stub_module_to_pb2_module(stub_module_name: str) -> str:
    """
    例:
        "cobotta2.server_grpc.joypad_pb2_grpc" -> "cobotta2.server_grpc.joypad_pb2"
    """
    if stub_module_name.endswith("_pb2_grpc") is False:
        raise RuntimeError(
            f"stub module does not look like *_pb2_grpc: {stub_module_name}"
        )

    prefix = stub_module_name[: -len("_grpc")]
    return prefix


def _resolve_request_class_from_rpc(
    rpc: Any,
    *,
    stub_class: Type[Any],
    logger: XLogger,
) -> Type[Any]:
    """
    rpc (UnaryUnaryMultiCallable 等) から request message class を復元する。

    優先順位:
    1) rpc._request_deserializer / _request_serializer の束縛先(__self__) から具体クラス
    2) stub_class.__module__ ( *_pb2_grpc ) から *_pb2 を import し、
       "<RpcName>Request" を探す
    3) それも無ければ google.protobuf.empty_pb2.Empty を返す（最後の逃げ）
    """
    request_deserializer = getattr(rpc, "_request_deserializer", None)
    if request_deserializer is not None:
        owner = _get_bound_owner(request_deserializer)
        if owner is not None:
            if _is_protobuf_base_message_class(owner) is False:
                return owner

    request_serializer = getattr(rpc, "_request_serializer", None)
    if request_serializer is not None:
        owner = _get_bound_owner(request_serializer)
        if owner is not None:
            if _is_protobuf_base_message_class(owner) is False:
                return owner

    method_path = getattr(rpc, "_method", None)
    if method_path is None:
        raise RuntimeError("rpc has no _method; cannot resolve request class")

    rpc_name = _parse_rpc_name_from_method_path(method_path)
    request_name = f"{rpc_name}Request"

    stub_module_name = getattr(stub_class, "__module__", "")
    if stub_module_name == "":
        raise RuntimeError("stub_class has no __module__")

    pb2_module_name = _stub_module_to_pb2_module(stub_module_name)

    logger.info(
        f"[GrpcClient] resolve request: rpc_name={rpc_name}, pb2_module={pb2_module_name}"
    )

    pb2_module = importlib.import_module(pb2_module_name)

    if hasattr(pb2_module, request_name):
        return getattr(pb2_module, request_name)

    logger.info(
        f"[GrpcClient] request message not found: {pb2_module_name}.{request_name} -> fallback Empty"
    )
    return empty_pb2.Empty


class GrpcClient:
    _ctrl_class: type
    _stub_class: type
    _client_log_title: str

    def __init__(
        self,
        server_ip: str,
        server_port: int,
        logger: Optional[XLogger] = None,
    ) -> None:
        self._logger: XLogger = logger or XLogger()

        addr = f"{server_ip}:{server_port}"
        self._channel: grpc.Channel = grpc.insecure_channel(addr)
        self._stub: Any = self._stub_class(self._channel)

        self._logger.info(f"== Create {self._client_log_title}")
        self._logger.info(f" gRPC serer IP   = {server_ip}")
        self._logger.info(f" gRPC serer port = {server_port}")

        self._logger.info("bind_ctrl_method")
        self._bind_ctrl_methods()

    def is_connected(self, timeout: float = 0.5) -> bool:
        try:
            grpc.channel_ready_future(self._channel).result(timeout=timeout)
            return True
        except Exception:
            return False

    def _bind_ctrl_methods(self) -> None:
        for name, method in inspect.getmembers(self._ctrl_class, inspect.isfunction):
            if name.startswith("_"):
                continue

            rpc_name = _to_rpc_name(name)
            has_rpc = hasattr(self._stub, rpc_name)

            self._logger.info(
                f"[GrpcClient] scan ctrl method: {name} -> {rpc_name}, has_rpc={has_rpc}"
            )

            if has_rpc is False:
                continue

            rpc = getattr(self._stub, rpc_name)
            sig = inspect.signature(method)

            dispatcher = self._make_dispatcher(
                method_name=name,
                rpc_name=rpc_name,
                sig=sig,
                rpc=rpc,
            )
            setattr(self, name, dispatcher)

    def _is_protobuf_message(self, obj: Any) -> bool:
        descriptor = getattr(obj, "DESCRIPTOR", None)
        if descriptor is None:
            return False
        fields = getattr(descriptor, "fields", None)
        if fields is None:
            return False
        return True

    def _unwrap_response(self, resp: Any) -> Any:
        """
        gRPC Response を ctrl 側の戻り値に正規化して返す。

        ルール:
        - resp.ok があれば bool を返す
        - フィールドが 1 個:
            - repeated なら list
            - それ以外はスカラ
        - フィールドが複数: dict を返す
        - protobuf 以外: そのまま返す
        """
        if self._is_protobuf_message(resp) is False:
            return resp

        if hasattr(resp, "ok"):
            ok_val = getattr(resp, "ok")
            return bool(ok_val)

        fields = list(resp.DESCRIPTOR.fields)

        if len(fields) == 1:
            field = fields[0]
            value = getattr(resp, field.name)

            if field.label == field.LABEL_REPEATED:
                return list(value)

            return value

        out: Dict[str, Any] = {}
        for field in fields:
            value = getattr(resp, field.name)
            if field.label == field.LABEL_REPEATED:
                out[field.name] = list(value)
            else:
                out[field.name] = value
        return out

    def _make_dispatcher(
        self,
        *,
        method_name: str,
        rpc_name: str,
        sig: inspect.Signature,
        rpc: Any,
    ) -> Callable[..., Any]:
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
            self._logger.debug(f"[GrpcClient] CALL {method_name}() begin")
            self._logger.debug(f"[GrpcClient] args={args}, kwargs={kwargs}")

            try:
                bound = sig.bind_partial(None, *args, **kwargs)
                bound.apply_defaults()

                req_kwargs: Dict[str, Any] = {}
                for k, v in bound.arguments.items():
                    if k == "self":
                        continue
                    req_kwargs[k] = v

                self._logger.debug(f"[GrpcClient] req_kwargs={req_kwargs}")
                request = self._build_request(request_cls, req_kwargs)
                self._logger.debug(
                    f"[GrpcClient] request built: type={type(request)}, module={type(request).__module__}"
                )

                self._logger.debug("[GrpcClient] rpc call start")
                resp = rpc(request)
                self._logger.debug("[GrpcClient] rpc call done")

                unwrapped = self._unwrap_response(resp)
                return unwrapped

            except Exception as e:
                self._logger.error(
                    f"[{self.__class__.__name__}] {method_name} failed: {e}"
                )
                return False

        _method.__name__ = method_name
        _method.__signature__ = sig
        return _method

    def _build_request(
        self,
        request_cls: Type[Any],
        req_kwargs: Dict[str, Any],
    ) -> Any:
        """
        SendDpose のような repeated フィールド 1 個構成を正しく扱う
        """
        try:
            return request_cls(**req_kwargs)
        except Exception:
            req = request_cls()

            if len(req_kwargs) == 1:
                key, value = next(iter(req_kwargs.items()))
                field = req.DESCRIPTOR.fields_by_name.get(key)
                if field is not None:
                    if field.label == field.LABEL_REPEATED:
                        getattr(req, key).extend(value)
                        return req

            for k, v in req_kwargs.items():
                setattr(req, k, v)
            return req