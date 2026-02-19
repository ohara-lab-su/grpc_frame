#!/usr/bin/env python
"""
Kengo NAKADA
kengo.nakada@mat.shimane-u.ac.jp
kengo.nakada@gmail.com

COM スレッド境界を守って gRPC から ctrl を安全に呼び出す補助モジュール。

windows の COM のインスタンスを別スレッドで回す
（コンストラクタとメソッドを別スレッド）とおかしくなる。

そのため gRPC などでは別スレッドでハンドラが動くのでCOM を破壊する。
その対策で制御側で com 読み込みではなくて gRPCハンドラースレッドで
COMを初期化するようにする

gRPC Client
  --> grpc_server._ControlServicer (gRPC worker thread)
  --> ThreadSafeCtrlProxy
  --> ComExecutionRunner (queueで直列化)
  --> COM ctrl object (同一スレッドで生成/実行)

要点
- gRPC worker thread から COM を直接触らない
- COM の生成/実行は ComExecutionRunner の専用スレッドに固定
- grpc_server は汎用のまま、COM制約は grpc_com 側で吸収する
- gRPC サーバーは ThreadPool 上で handler が動くため、ctrl を直接渡すと
  呼び出しスレッドが分散し、COM 破壊や不安定動作の原因になる。

設計
- COM 制約はこのモジュール内に閉じ込める。
- ComExecutionRunner が COM 専用スレッドを持ち、ctrl 生成とメソッド実行を一本化する。
- ThreadSafeCtrlProxy は gRPC 側に見せる代理で、呼び出しを runner に委譲する。
- create_com_grpc_server は既存 create_grpc_server と組み合わせるための薄い組み立て関数。
"""

from __future__ import annotations

import inspect
import queue
import threading
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence, Tuple


def _format_exception(
    e: BaseException,
) -> str:
    """例外をスタックトレース付き文字列へ整形する。"""
    exc_type = type(e)
    tb = e.__traceback__
    return "".join(traceback.format_exception(exc_type, e, tb))


@dataclass(frozen=True)
class _CallItem:
    """COM 専用スレッドへ渡す 1 回分の実行要求。"""

    method_name: str
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]
    done_event: threading.Event
    box: Dict[str, Any]


class ComExecutionRunner:
    """
    ctrl を COM 専用スレッドで生成・実行するランナー。

    役割:
    - ctrl_factory の実行を COM 専用スレッドへ固定する
    - gRPC 側からの呼び出しをキューで直列化して実行する
    - public メソッド一覧とシグネチャを introspection 用に保持する
    """

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

        # event 有無
        self._has_set_event_bus: bool = False

        self._thread = threading.Thread(
            target=self._run,
            name="ComExecutionRunner",
            daemon=True,
        )
        self._thread.start()

    def _try_initialize_com(
        self,
    ) -> bool:
        """pythoncom が使える環境なら CoInitialize() を呼ぶ。"""

        try:
            import pythoncom  # type: ignore

            pythoncom.CoInitialize()
            self._logger.info("[ComExecutionRunner] CoInitialize done")
            return True
        except Exception as e:
            self._logger.warning(f"[ComExecutionRunner] CoInitialize skipped: {e}")
            return False

    def _try_uninitialize_com(
        self,
    ) -> None:
        """CoInitialize() 済みの場合のみ後始末する。"""

        try:
            import pythoncom  # type: ignore

            pythoncom.CoUninitialize()
            self._logger.info("[ComExecutionRunner] CoUninitialize done")
        except Exception as e:
            self._logger.warning(f"[ComExecutionRunner] CoUninitialize skipped: {e}")

    def _run(self) -> None:
        """
        COM 専用ワーカースレッド本体。

        重要:
        - ctrl 生成と実行をこのスレッド内に限定する
        - 初期化完了時点で ready_event を立てる
        """
        com_initialized = False
        try:
            com_initialized = self._try_initialize_com()

            self._logger.info("[ComExecutionRunner] create ctrl (COM thread)")
            self._ctrl = self._ctrl_factory()

            # Event の有無
            try:
                self._has_set_event_bus: bool = callable(
                    getattr(
                        self._ctrl,
                        "_set_event_bus",
                        None,
                    )
                )
            except Exception:
                self._has_set_event_bus: bool = False

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

    @staticmethod
    def _collect_public_method_names(
        ctrl: Any,
    ) -> Tuple[str, ...]:
        """ctrl の public callable 名を収集してソート返却する。"""

        names: list[str] = []
        for name in dir(ctrl):
            if name.startswith("_"):
                continue
            try:
                # property getter が動く
                # attr = getattr(ctrl, name)

                static_member = inspect.getattr_static(
                    ctrl,
                    name,
                )  # <- getter を動かさない
            except Exception:
                continue

            if isinstance(static_member, property):
                continue

                # if callable(attr):
            if callable(static_member):
                names.append(name)

        names.sort()
        return tuple(names)

    @staticmethod
    def _collect_signatures(
        ctrl: Any,
        names: Sequence[str],
    ) -> Dict[str, inspect.Signature]:
        """公開メソッドの inspect.Signature を収集する。"""

        sigs: Dict[str, inspect.Signature] = {}
        for name in names:
            try:
                # target = getattr(ctrl, name)
                static_member = inspect.getattr_static(ctrl, name)
            except Exception:
                continue

            if isinstance(static_member, property):
                continue

            if not callable(static_member):
                continue

            try:
                target = getattr(
                    ctrl, name
                )  # callable のみ実体化（propertyは除外済み）
            except Exception:
                continue

            try:
                sigs[name] = inspect.signature(target)
            except Exception:
                sigs[name] = inspect.Signature()

            # if callable(target):
            #     try:
            #         sigs[name] = inspect.signature(target)
            #     except Exception:
            #         sigs[name] = inspect.Signature()
        return sigs

    def _execute_one(
        self,
        item: _CallItem,
    ) -> None:
        """キューから受け取った 1 呼び出しを COM スレッド上で実行する。"""

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

    def _ensure_ready_or_raise(
        self,
        timeout: Optional[float],
    ) -> None:
        """起動完了チェック。初期化失敗時は詳細例外を再送出する。"""

        if not self._ready_event.wait(timeout=timeout):
            raise TimeoutError("ComExecutionRunner initialization timed out")
        if self._startup_error is not None:
            raise RuntimeError(self._startup_error)
        if self._ctrl is None:
            raise RuntimeError("ctrl is not initialized")

    def wait_ready(
        self,
        timeout: Optional[float] = None,
    ) -> bool:
        """runner が利用可能かを bool で返す。"""

        try:
            self._ensure_ready_or_raise(timeout=timeout)
            return True
        except Exception:
            return False

    def get_startup_error(
        self,
    ) -> Optional[str]:
        """起動エラー文字列（なければ None）を返す。"""

        self._ready_event.wait()
        return self._startup_error

    def list_public_methods(
        self,
        timeout: Optional[float] = None,
    ) -> Tuple[str, ...]:
        """public メソッド名一覧を返す。"""

        self._ensure_ready_or_raise(timeout=timeout)
        return self._public_method_names

    def get_signature(
        self, name: str, timeout: Optional[float] = None
    ) -> inspect.Signature:
        """指定メソッドのシグネチャを返す（未知なら空シグネチャ）。"""

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
        """
        指定メソッドを COM スレッドへ委譲して実行する。

        Returns:
        - (True, result, "")
        - (False, None, error_message)
        """

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

        if box.get("ok"):
            return True, box.get("result"), ""

        err = box.get("error") or "unknown error"
        return False, None, str(err)

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._queue.put(None)
        self._thread.join()

    def supports_set_event_bus(
        self,
        timeout: Optional[float] = None,
    ) -> bool:
        """ctrl が _set_event_bus を実装しているかを返す。"""

        self._ensure_ready_or_raise(timeout=timeout)
        return self._has_set_event_bus


class ThreadSafeCtrlProxy:
    """
    gRPC 側へ渡す ctrl 代理。

    - Describe 用 introspection を満たすため、公開メソッドを属性として生やす
    - 実呼び出しはすべて runner.call(...) に委譲する
    """

    def __init__(
        self,
        runner: ComExecutionRunner,
        *,
        ready_timeout: Optional[float] = 10.0,
    ) -> None:
        self._runner = runner
        self._ready_timeout = ready_timeout
        self._bind_public_methods()

    def _bind_public_methods(
        self,
    ) -> None:
        """初期化時に public API を一括バインドする。"""

        for name in self._runner.list_public_methods(timeout=self._ready_timeout):
            setattr(self, name, self._build_method(name))

    def _build_method(
        self,
        name: str,
    ):
        """runner に委譲する callable を 1 つ生成する。"""

        sig = self._runner.get_signature(name, timeout=self._ready_timeout)

        def _method(*args: Any, **kwargs: Any) -> Any:
            ok, result, error = self._runner.call(name, args, kwargs, timeout=None)
            if ok:
                return result
            raise RuntimeError(error)

        _method.__name__ = name
        _method.__signature__ = sig  # type: ignore[attr-defined]
        return _method

    def __dir__(
        self,
    ) -> Sequence[str]:
        """Describe/introspection のために runner 側メソッド名を露出する。"""

        names = set(super().__dir__())
        names.update(self._runner.list_public_methods(timeout=self._ready_timeout))
        return sorted(names)

    def __getattr__(
        self,
        name: str,
    ):
        """未バインドメソッドへの遅延対応。"""

        if name.startswith("_"):
            raise AttributeError(name)
        method = self._build_method(name)
        setattr(self, name, method)
        return method

    def _set_event_bus(
        self,
        event_bus: Any,
    ) -> None:
        """
        gRPC フレームからの EventBus 注入点。

        ctrl 側が _set_event_bus 非実装の場合は no-op とする。
        """
        if not self._runner.supports_set_event_bus(
            timeout=self._ready_timeout,
        ):
            return

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
    """
    COM 対応版 gRPC サーバーを組み立てるヘルパー。

    処理:
    1. ComExecutionRunner を起動して ctrl を COM スレッドで生成
    2. ThreadSafeCtrlProxy で ctrl をラップ
    3. 既存 create_grpc_server(ctrl_obj=proxy) へ接続
    """
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
