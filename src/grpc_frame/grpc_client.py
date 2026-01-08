# grpc_frame/client.py
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Type
import inspect

import grpc

import grpc_frame.dispatch_core as core
import grpc_frame.util_client as client_util

from x_logger import XLogger


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
            if name.startswith("_") is True:
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
        request_cls: Type[Any] = client_util.resolve_request_class_from_rpc(
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
