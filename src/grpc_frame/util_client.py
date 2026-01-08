# grpc_frame/client_util.py
from __future__ import annotations

from typing import Any, Optional, Type
import importlib
import inspect

from google.protobuf import empty_pb2

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


def resolve_request_class_from_rpc(
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
