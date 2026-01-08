# grpc_frame/grpc_client.py
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Type
import importlib
import inspect

import grpc
from google.protobuf import empty_pb2


import grpc_frame.dispatch_core as core
from x_logger import XLogger


def _normalize_method_path(method_path: Any) -> str:
    if isinstance(method_path, bytes) is True:
        try:
            return method_path.decode("utf-8")
        except Exception:
            return method_path.decode("latin-1", errors="replace")

    if isinstance(method_path, str) is True:
        return method_path

    return str(method_path)


def _parse_rpc_name_from_method_path(method_path: Any) -> str:
    path: str = _normalize_method_path(method_path)
    parts: list[str] = path.split("/")
    if len(parts) < 2:
        raise ValueError(f"unexpected rpc method path: {path}")

    rpc_name: str = parts[-1]
    if rpc_name == "":
        raise ValueError(f"empty rpc name: {path}")

    return rpc_name


def _stub_module_to_pb2_module(stub_module_name: str) -> str:
    if stub_module_name.endswith("_pb2_grpc") is False:
        raise RuntimeError(
            f"stub module does not look like *_pb2_grpc: {stub_module_name}"
        )

    prefix: str = stub_module_name[: -len("_grpc")]
    return prefix


def _get_owner_from_serializer(serializer: Any) -> Optional[type]:
    owner: Any = getattr(serializer, "__self__", None)
    if owner is None:
        return None

    is_class: bool = inspect.isclass(owner)
    if is_class is False:
        return None

    return owner


def _is_protobuf_base_message_class(cls: Type[Any]) -> bool:
    module_name: str = getattr(cls, "__module__", "")
    class_name: str = getattr(cls, "__name__", "")
    if module_name != "google._upb._message":
        return False
    if class_name != "Message":
        return False
    return True


def _resolve_request_class_from_rpc(
    rpc: Any,
    *,
    stub_class: Type[Any],
    logger: XLogger,
) -> Type[Any]:
    request_deserializer: Any = getattr(rpc, "_request_deserializer", None)
    if request_deserializer is not None:
        owner = _get_owner_from_serializer(request_deserializer)
        if owner is not None:
            is_base: bool = _is_protobuf_base_message_class(owner)
            if is_base is False:
                return owner

    request_serializer: Any = getattr(rpc, "_request_serializer", None)
    if request_serializer is not None:
        owner2 = _get_owner_from_serializer(request_serializer)
        if owner2 is not None:
            is_base2: bool = _is_protobuf_base_message_class(owner2)
            if is_base2 is False:
                return owner2

    method_path: Any = getattr(rpc, "_method", None)
    if method_path is None:
        logger.info("[GrpcClient] rpc has no _method; fallback Empty")
        return empty_pb2.Empty

    rpc_name: str = _parse_rpc_name_from_method_path(method_path)
    request_name: str = f"{rpc_name}Request"

    stub_module_name: str = getattr(stub_class, "__module__", "")
    if stub_module_name == "":
        raise RuntimeError("stub_class has no __module__")

    pb2_module_name: str = _stub_module_to_pb2_module(stub_module_name)

    logger.info(
        f"[GrpcClient] resolve request: rpc_name={rpc_name}, pb2_module={pb2_module_name}"
    )

    pb2_module = importlib.import_module(pb2_module_name)

    has_req: bool = hasattr(pb2_module, request_name)
    if has_req is True:
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

        addr: str = f"{server_ip}:{server_port}"
        self._channel: grpc.Channel = grpc.insecure_channel(addr)
        self._stub: Any = self._stub_class(self._channel)

        self._logger.info(f"== Create {self._client_log_title}")
        self._logger.info(f" gRPC server = {server_ip}:{server_port}")

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

            rpc_name: str = core.ctrl_method_to_rpc_name(name)
            has_rpc: bool = hasattr(self._stub, rpc_name)

            self._logger.info(
                f"[GrpcClient] scan ctrl method: {name} -> {rpc_name}, has_rpc={has_rpc}"
            )

            if has_rpc is False:
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

        Args:
            method_name:
            rpc_name:
            sig:
            rpc:

        Returns:

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

                req_kwargs: Dict[str, Any] = {}
                for k, v in bound.arguments.items():
                    if k == "self":
                        continue
                    req_kwargs[k] = v

                self._logger.info(f"[GrpcClient] req_kwargs={req_kwargs}")

                request = core.build_request_message(request_cls, req_kwargs)

                self._logger.info(f"[GrpcClient][DEBUG] request content = {request}")

                self._logger.info(
                    f"[GrpcClient] request built: type={type(request)}, module={type(request).__module__}"
                )

                self._logger.info("[GrpcClient] rpc call start")
                resp = rpc(request)
                self._logger.info("[GrpcClient] rpc call done")

                return core.unwrap_response(resp)

            except Exception as e:
                self._logger.error(
                    f"[{self.__class__.__name__}] {method_name} failed: {e}"
                )
                return False

        _method.__name__ = method_name
        _method.__signature__ = sig
        return _method
