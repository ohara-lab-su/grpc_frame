#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
K.NAKADA, kengo.nakada@gmail.com, kengo.nakada@mat.shimane-u.ac.jp

EventBus: 軽量な in-process イベント配信機構。

- publish: イベントを配信
- subscribe: イベントを generator で受信
- スレッド間での待機/通知に Condition を使用
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Deque, Dict, Iterator, List, Optional
from collections import deque
import threading
import time


@dataclass(frozen=True)
class EventItem:
    """EventBus が配信するイベント1件のデータ構造。"""

    topic: str
    payload_obj: Any
    ts_ns: int
    source: str


class _Subscriber:
    def __init__(
        self,
        topic: str,
        *,
        once: bool,
        source: str,
    ) -> None:
        """
        1トピックの購読状態を保持する内部クラス。
        Condition + queue で publish/subscribe を同期する。
        """

        self.topic: str = topic
        self.once: bool = once
        self.source: str = source
        self._cond: threading.Condition = threading.Condition()
        self._queue: Deque[EventItem] = deque()
        self._closed: bool = False

    def close(self) -> None:
        # 待機中の購読者を解除して終了させる
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    def push(self, item: EventItem) -> None:
        # publish からのイベントをキューへ
        with self._cond:
            if self._closed:
                return
            self._queue.append(item)
            self._cond.notify_all()

    def pop_wait(self) -> Optional[EventItem]:
        # イベントが来るまでブロックして待機
        with self._cond:
            while True:
                if self._closed:
                    return None
                if len(self._queue) > 0:
                    item: EventItem = self._queue.popleft()
                    return item
                self._cond.wait()


class EventBus:
    """
    in-process のイベント配信ハブ。

    - publish: topic に紐づく購読者へ配信
    - subscribe: generator 形式でイベントを取得
    """

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._subscribers: List[_Subscriber] = []

    def publish(
        self,
        topic: str,
        payload_obj: Any,
        *,
        source: str = "",
    ) -> None:
        """
        イベントを publish して、該当トピックの購読者へ通知する。

        Args:
            topic: トピック名
            payload_obj: 任意の payload
            source: 発生元識別子
        """
        # 配信時刻（ナノ秒）
        ts_ns: int = time.time_ns()
        item: EventItem = EventItem(
            topic=topic,
            payload_obj=payload_obj,
            ts_ns=ts_ns,
            source=source,
        )

        # 購読者リストのスナップショットを取る（ロック時間最小化）
        subs_snapshot: List[_Subscriber] = []
        with self._lock:
            subs_snapshot = list(self._subscribers)

        # 該当トピックにのみ配信
        for sub in subs_snapshot:
            if sub.topic != topic:
                continue
            sub.push(item)

    def subscribe(
        self,
        topic: str,
        *,
        once: bool = False,
        source: str = "",
        cancel_event: Optional[threading.Event] = None,
    ) -> Iterator[EventItem]:
        """
        指定トピックを購読し、EventItem を generator で返す。

        Args:
            topic: 購読するトピック
            once: True の場合は1件受信したら終了
            source: 発生元フィルタ（未使用だが拡張用）
            cancel_event: 外部から購読解除するための Event

        Yields:
            EventItem
        """
        # 購読状態を生成
        sub: _Subscriber = _Subscriber(
            topic=topic,
            once=once,
            source=source,
        )

        with self._lock:
            # 購読者リストに登録
            self._subscribers.append(sub)

        try:
            while True:
                if cancel_event is not None:
                    if cancel_event.is_set():
                        break

                # イベントを待機して取得
                item = sub.pop_wait()
                if item is None:
                    break

                yield item

                if sub.once:
                    break

        finally:
            # 終了時に購読解除
            sub.close()

            with self._lock:
                new_list: List[_Subscriber] = []
                for s in self._subscribers:
                    if s is sub:
                        continue
                    new_list.append(s)
                self._subscribers = new_list
