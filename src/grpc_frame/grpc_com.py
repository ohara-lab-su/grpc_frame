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

gRPCスレッド
   ↓
_ControlServicer
   ↓ getattr / call
ThreadSafeCtrlProxy
   ↓
ComExecutionRunner
   ↓
CobottaCtrl（COM専用スレッド）

gRPC から COM オブジェクトを安全に呼び出すための補助である。

目的は「COM を生成したスレッド以外から COM を触らない」を徹底し、
gRPC 側（ThreadPoolExecutor の任意スレッド）からの呼び出しをすべて
COM 専用スレッドへ直列化して委譲することである。

- ComExecutionRunner: COM 専用スレッドで ctrl を生成し、そのスレッドでのみ実行する
- ThreadSafeCtrlProxy: ctrl の public API を動的に透過し、runner に委譲する

注意:
- ctrl 側が pythoncom.CoInitialize/CoUninitialize を管理している場合がある。
  その場合 runner 側で pythoncom を触ると二重管理になり得るため、
  com_initialize_mode="none" を既定とする（ctrl 側に管理を委ねる）。
"""

from __future__ import annotations

import inspect
import queue
import threading
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence, Tuple


def _format_exception(e: BaseException) -> str:
    """例外を型名とスタックトレース込みの文字列に整形する。"""
    exc_type = type(e)
    tb = e.__traceback__
    return "".join(traceback.format_exception(exc_type, e, tb))


@dataclass(frozen=True)
class _CallItem:
    """runner のキューに入れる呼び出し要求である。"""

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
        logger: Optional[Any] = None,
        log_level: Optional[str] = None,
        com_initialize_mode: str = "none",
    ) -> None:
        """
        Args:
            ctrl_factory: COM スレッド上で実行される ctrl 生成関数である。
            logger: ロガーである。
            log_level: ログレベルである。
            com_initialize_mode:
                "none" の場合 runner は pythoncom を触らない。
                "runner" の場合 runner が CoInitialize/CoUninitialize を行う。
        """
        if logger is None:
            import logging

            level = log_level
            if level is None:
                level = "INFO"
            logging.basicConfig(level=str(level).upper())
            logger = logging.getLogger(__name__)

        self._logger: Any = logger
        self._ctrl_factory: Callable[[], Any] = ctrl_factory

        self._com_initialize_mode: str = str(com_initialize_mode)

        self._queue: queue.Queue[Optional[_CallItem]] = queue.Queue()
        self._running: bool = True

        self._ready_event: threading.Event = threading.Event()

        self._ctrl: Optional[Any] = None
        self._public_method_names: Tuple[str, ...] = tuple()
        self._signatures: Dict[str, inspect.Signature] = {}

        self._thread: threading.Thread = threading.Thread(
            target=self._run,
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        pythoncom = None
        co_initialized: bool = False

        try:
            if self._com_initialize_mode == "runner":
                try:
                    import pythoncom as _pythoncom  # type: ignore

                    pythoncom = _pythoncom
                except Exception:
                    pythoncom = None

                if pythoncom is not None:
                    pythoncom.CoInitialize()
                    co_initialized = True

            self._ctrl = self._ctrl_factory()

            self._public_method_names = self._collect_public_method_names(self._ctrl)
            self._signatures = self._collect_signatures(
                self._ctrl, self._public_method_names
            )

            self._ready_event.set()

            while self._running:
                item = self._queue.get()
                if item is None:
                    break
                self._execute_one(item)

        except Exception as e:
            self._logger.error(_format_exception(e))
            self._ready_event.set()

        finally:
            if self._com_initialize_mode == "runner":
                if pythoncom is not None:
                    if co_initialized:
                        try:
                            pythoncom.CoUninitialize()
                        except Exception:
                            pass

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

            target = getattr(self._ctrl, item.method_name)
            result = target(*item.args, **item.kwargs)

            item.box["ok"] = True
            item.box["result"] = result
            item.box["error"] = ""

        except Exception as e:
            item.box["ok"] = False
            item.box["result"] = None
            item.box["error"] = _format_exception(e)

        finally:
            item.done_event.set()

    def wait_ready(self, timeout: Optional[float] = None) -> bool:
        return bool(self._ready_event.wait(timeout=timeout))

    def list_public_methods(self, timeout: Optional[float] = None) -> Tuple[str, ...]:
        self.wait_ready(timeout=timeout)
        return self._public_method_names

    def get_signature(
        self,
        name: str,
        timeout: Optional[float] = None,
    ) -> inspect.Signature:
        self.wait_ready(timeout=timeout)
        sig = self._signatures.get(name)
        if sig is None:
            return inspect.Signature()
        return sig

    def call(
        self,
        name: str,
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        *,
        timeout: Optional[float] = None,
    ) -> Tuple[bool, Any, str]:
        done_event = threading.Event()
        box: Dict[str, Any] = {}

        item = _CallItem(
            method_name=name,
            args=args,
            kwargs=kwargs,
            done_event=done_event,
            box=box,
        )

        self._queue.put(item)

        done_event.wait(timeout=timeout)

        ok_val = box.get("ok")
        if ok_val is True:
            return True, box.get("result"), ""

        err = box.get("error")
        if err is None:
            err = "unknown error"
        return False, None, str(err)

    def stop(self) -> None:
        self._running = False
        self._queue.put(None)
        self._thread.join()


class ThreadSafeCtrlProxy:
    """gRPC 側から見える ctrl 代理である。

    この proxy は次を満たすことで、Describe（dispatch_core 側の introspection）を成立させる。
    - dir() が runner の public メソッド名を返す
    - getattr() が runner.call() に委譲する callable を返す
    - callable には __signature__ を付与する
    """

    def __init__(
        self,
        runner: ComExecutionRunner,
        *,
        ready_timeout: Optional[float] = 10.0,
    ) -> None:
        self._runner: ComExecutionRunner = runner
        self._ready_timeout: Optional[float] = ready_timeout

    def __dir__(self) -> Sequence[str]:
        names = self._runner.list_public_methods(timeout=self._ready_timeout)
        return list(names)

    def __getattr__(self, name: str):
        names = self._runner.list_public_methods(timeout=self._ready_timeout)
        if name not in names:
            raise AttributeError(name)

        sig = self._runner.get_signature(name, timeout=self._ready_timeout)

        def _method(*args: Any, **kwargs: Any) -> Any:
            ok, result, error = self._runner.call(
                name,
                args,
                kwargs,
                timeout=None,
            )
            if ok:
                return result
            raise RuntimeError(error)

        _method.__name__ = name
        _method.__signature__ = sig  # type: ignore[attr-defined]
        return _method
