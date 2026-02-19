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

gRPC の ThreadPoolExecutor スレッドから COM を直接触らないための補助である。

ComExecutionRunner が COM 専用スレッドで ctrl を生成し、
すべての呼び出しをキュー経由で直列化して同一スレッドで実行する。

ThreadSafeCtrlProxy は ctrl の public API を「列挙できる形」で露出し、
実行は runner に委譲する。
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
    ) -> None:
        if logger is None:
            import logging

            level = log_level
            if level is None:
                level = "INFO"
            logging.basicConfig(level=str(level).upper())
            logger = logging.getLogger(__name__)

        self._logger: Any = logger
        self._ctrl_factory: Callable[[], Any] = ctrl_factory

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
        pythoncom: Optional[Any] = None
        co_initialized: bool = False

        try:
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
                self._ctrl,
                self._public_method_names,
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
            if pythoncom is not None:
                if co_initialized:
                    try:
                        pythoncom.CoUninitialize()
                    except Exception:
                        pass

    def _collect_public_method_names(self, ctrl: Any) -> Tuple[str, ...]:
        names_list: list[str] = []
        for name in dir(ctrl):
            if name.startswith("_"):
                continue
            try:
                attr = getattr(ctrl, name)
            except Exception:
                continue
            if callable(attr):
                names_list.append(name)
        names_list.sort()
        return tuple(names_list)

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

    Describe が列挙型 introspection を用いても public メソッドが見えるように、
    初期化時点で proxy 自身へ public メソッド実体を setattr で生やす。
    """

    def __init__(
        self,
        runner: ComExecutionRunner,
        *,
        ready_timeout: Optional[float] = 10.0,
    ) -> None:
        self._runner: ComExecutionRunner = runner
        self._ready_timeout: Optional[float] = ready_timeout
        self._install_public_methods()

    def _install_public_methods(self) -> None:
        self._runner.wait_ready(timeout=self._ready_timeout)

        names = self._runner.list_public_methods(timeout=self._ready_timeout)
        for name in names:
            func = self._make_method(name)
            setattr(self, name, func)

    def _make_method(self, name: str) -> Callable[..., Any]:
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

    def __dir__(self) -> Sequence[str]:
        base = set(super().__dir__())
        names = self._runner.list_public_methods(timeout=self._ready_timeout)
        for name in names:
            base.add(name)
        return sorted(base)
