#!/usr/bin/env python
"""
Kengo NAKADA
kengo.nakada@mat.shimane-u.ac.jp
kengo.nakada@gmail.com

windows の COM のインスタンスを
別スレッドで回す（コンストラクタとメソッドを別スレッド）
とおかしくなる。

そのため gRPC などでは別スレッドでハンドラが動くので
COM を破壊する。その対策で制御側で com 読み込みではなくて
gRPCハンドラースレッドでCOMを初期化するようにする

そのためのサポート
# 既存 _ControlServicer と共存する Proxy

gRPC から COM オブジェクトを安全に呼び出すための補助クラス群である。

目的は「COM を生成したスレッド以外から COM を触らない」を徹底し、
gRPC 側の ThreadPoolExecutor スレッドからの呼び出しをすべて
COM 専用スレッドへ直列化して委譲することである。

- ComExecutionRunner: COM 専用スレッドを立て、キューで呼び出しを処理する
- ThreadSafeCtrlProxy: ctrl の public API を動的に透過し、runner に委譲する
"""

from __future__ import annotations

import inspect
import queue
import threading
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence, Tuple


def _format_exception(e: BaseException) -> str:
    exc_type = type(e)
    tb = e.__traceback__
    return "".join(traceback.format_exception(exc_type, e, tb))


@dataclass(frozen=True)
class _CallItem:
    method_name: str
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]
    done_event: threading.Event
    box: Dict[str, Any]


class ComExecutionRunner:
    """COM 専用スレッドで ctrl を生成し、そのスレッドでのみ実行するランナーである。"""

    def __init__(
        self,
        ctrl_factory: Callable[[], Any],
        *,
        after_create: Optional[Callable[[Any], None]] = None,
        logger: Optional[Any] = None,
        log_level: Optional[str] = None,
    ) -> None:
        if logger is None:
            import logging

            level = log_level or "INFO"
            logging.basicConfig(level=str(level).upper())
            logger = logging.getLogger(__name__)

        self._logger: Any = logger
        self._ctrl_factory: Callable[[], Any] = ctrl_factory
        self._after_create: Optional[Callable[[Any], None]] = after_create

        self._queue: queue.Queue[Optional[_CallItem]] = queue.Queue()
        self._ready_event: threading.Event = threading.Event()

        self._ctrl: Optional[Any] = None
        self._public_method_names: Tuple[str, ...] = tuple()
        self._signatures: Dict[str, inspect.Signature] = {}
        self._startup_error: Optional[str] = None
        self._stopped: bool = False

        self._thread = threading.Thread(
            target=self._run,
            name="ComExecutionRunner",
            daemon=True,
        )
        self._thread.start()

    def _try_initialize_com(self) -> bool:
        try:
            import pythoncom  # type: ignore

            pythoncom.CoInitialize()
            self._logger.info("[ComExecutionRunner] CoInitialize done")
            return True
        except Exception as e:
            self._logger.warning(f"[ComExecutionRunner] CoInitialize skipped: {e}")
            return False

    def _try_uninitialize_com(self) -> None:
        try:
            import pythoncom  # type: ignore

            pythoncom.CoUninitialize()
            self._logger.info("[ComExecutionRunner] CoUninitialize done")
        except Exception as e:
            self._logger.warning(f"[ComExecutionRunner] CoUninitialize skipped: {e}")

    def _run(self) -> None:
        com_initialized = False
        try:
            com_initialized = self._try_initialize_com()

            self._logger.info("[ComExecutionRunner] create ctrl (COM thread)")
            self._ctrl = self._ctrl_factory()

            if self._after_create is not None:
                self._logger.info("[ComExecutionRunner] after_create start")
                self._after_create(self._ctrl)
                self._logger.info("[ComExecutionRunner] after_create done")

            self._public_method_names = self._collect_public_method_names(self._ctrl)
            self._signatures = self._collect_signatures(
                self._ctrl, self._public_method_names
            )

            self._logger.info(
                f"[ComExecutionRunner] ready: public_methods={len(self._public_method_names)}"
            )
            self._ready_event.set()  # <- ここが重要（ready時点でセット）

            while True:
                item = self._queue.get()
                if item is None:
                    break
                self._execute_one(item)

        except Exception as e:
            self._startup_error = _format_exception(e)
            self._logger.error(self._startup_error)
            self._ready_event.set()

        finally:
            self._ready_event.set()
            if com_initialized:
                self._try_uninitialize_com()

    def _collect_public_method_names(self, ctrl: Any) -> Tuple[str, ...]:
        names: list[str] = []
        for name in dir(ctrl):
            if name.startswith("_"):
                continue
            try:
                attr = getattr(ctrl, name)
            except Exception:
                continue
            if callable(attr):
                names.append(name)
        names.sort()
        return tuple(names)

    def _collect_signatures(
        self,
        ctrl: Any,
        names: Sequence[str],
    ) -> Dict[str, inspect.Signature]:
        sigs: Dict[str, inspect.Signature] = {}
        for name in names:
            try:
                target = getattr(ctrl, name)
            except Exception:
                continue
            if callable(target):
                try:
                    sigs[name] = inspect.signature(target)
                except Exception:
                    sigs[name] = inspect.Signature()
        return sigs

    def _execute_one(self, item: _CallItem) -> None:
        try:
            if self._ctrl is None:
                raise RuntimeError("ctrl is not initialized")

            self._logger.info(
                f"[ComExecutionRunner][{item.method_name}] call args={item.args} kwargs={item.kwargs}"
            )
            target = getattr(self._ctrl, item.method_name)
            result = target(*item.args, **item.kwargs)

            item.box["ok"] = True
            item.box["result"] = result
            item.box["error"] = ""
            self._logger.info(f"[ComExecutionRunner][{item.method_name}] done")

        except Exception as e:
            item.box["ok"] = False
            item.box["result"] = None
            item.box["error"] = _format_exception(e)
            self._logger.error(f"[ComExecutionRunner][{item.method_name}] failed")
            self._logger.error(item.box["error"])

        finally:
            item.done_event.set()

    def _ensure_ready_or_raise(self, timeout: Optional[float]) -> None:
        if not self._ready_event.wait(timeout=timeout):
            raise TimeoutError("ComExecutionRunner initialization timed out")
        if self._startup_error is not None:
            raise RuntimeError(self._startup_error)
        if self._ctrl is None:
            raise RuntimeError("ctrl is not initialized")

    def wait_ready(self, timeout: Optional[float] = None) -> bool:
        try:
            self._ensure_ready_or_raise(timeout=timeout)
            return True
        except Exception:
            return False

    def get_startup_error(self) -> Optional[str]:
        self._ready_event.wait()
        return self._startup_error

    def list_public_methods(self, timeout: Optional[float] = None) -> Tuple[str, ...]:
        self._ensure_ready_or_raise(timeout=timeout)
        return self._public_method_names

    def get_signature(
        self, name: str, timeout: Optional[float] = None
    ) -> inspect.Signature:
        self._ensure_ready_or_raise(timeout=timeout)
        return self._signatures.get(name, inspect.Signature())

    def call(
        self,
        name: str,
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        *,
        timeout: Optional[float] = None,
    ) -> Tuple[bool, Any, str]:
        if self._stopped:
            return False, None, "ComExecutionRunner is stopped"

        try:
            self._ensure_ready_or_raise(timeout=timeout)
        except Exception as e:
            return False, None, str(e)

        done_event = threading.Event()
        box: Dict[str, Any] = {}
        self._queue.put(
            _CallItem(
                method_name=name,
                args=args,
                kwargs=kwargs,
                done_event=done_event,
                box=box,
            )
        )

        completed = done_event.wait(timeout=timeout)
        if not completed:
            return False, None, f"timeout while waiting '{name}'"

        if box.get("ok") is True:
            return True, box.get("result"), ""

        err = box.get("error") or "unknown error"
        return False, None, str(err)

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._queue.put(None)
        self._thread.join()


class ThreadSafeCtrlProxy:
    """gRPC 側から見える ctrl 代理である。"""

    def __init__(
        self,
        runner: ComExecutionRunner,
        *,
        ready_timeout: Optional[float] = 10.0,
    ) -> None:
        self._runner = runner
        self._ready_timeout = ready_timeout
        self._bind_public_methods()

    def _bind_public_methods(self) -> None:
        for name in self._runner.list_public_methods(timeout=self._ready_timeout):
            setattr(self, name, self._build_method(name))

    def _build_method(self, name: str):
        sig = self._runner.get_signature(name, timeout=self._ready_timeout)

        def _method(*args: Any, **kwargs: Any) -> Any:
            ok, result, error = self._runner.call(name, args, kwargs, timeout=None)
            if ok:
                return result
            raise RuntimeError(error)

        _method.__name__ = name
        _method.__signature__ = sig  # type: ignore[attr-defined]
        return _method

    def __dir__(self) -> Sequence[str]:
        names = set(super().__dir__())
        names.update(self._runner.list_public_methods(timeout=self._ready_timeout))
        return sorted(names)

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        method = self._build_method(name)
        setattr(self, name, method)
        return method

    def _set_event_bus(self, event_bus: Any) -> None:
        ok, _result, error = self._runner.call(
            "_set_event_bus",
            (event_bus,),
            {},
            timeout=self._ready_timeout,
        )
        if not ok:
            raise RuntimeError(error)


def create_com_grpc_server(
    *,
    ctrl_factory: Callable[[], Any],
    after_create: Optional[Callable[[Any], None]] = None,
    ready_timeout: Optional[float] = 10.0,
    max_workers: int = 10,
    event_bus: Optional[Any] = None,
    logger: Optional[Any] = None,
    log_level: Optional[str] = None,
):
    from grpc_frame.grpc_server import create_grpc_server

    runner = ComExecutionRunner(
        ctrl_factory=ctrl_factory,
        after_create=after_create,
        logger=logger,
        log_level=log_level,
    )

    if not runner.wait_ready(timeout=ready_timeout):
        startup_error = runner.get_startup_error()
        runner.stop()
        if startup_error:
            raise RuntimeError(startup_error)
        raise TimeoutError("ComExecutionRunner initialization timed out")

    proxy = ThreadSafeCtrlProxy(
        runner=runner,
        ready_timeout=ready_timeout,
    )

    server = create_grpc_server(
        ctrl_obj=proxy,
        max_workers=max_workers,
        event_bus=event_bus,
        logger=logger,
        log_level=log_level,
    )
    return server, runner, proxy
