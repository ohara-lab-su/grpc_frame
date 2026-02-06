#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Deque, Dict, Iterator, List, Optional
from collections import deque
import threading
import time


@dataclass(frozen=True)
class EventItem:
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
        self.topic: str = topic
        self.once: bool = once
        self.source: str = source
        self._cond: threading.Condition = threading.Condition()
        self._queue: Deque[EventItem] = deque()
        self._closed: bool = False

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    def push(self, item: EventItem) -> None:
        with self._cond:
            if self._closed:
                return
            self._queue.append(item)
            self._cond.notify_all()

    def pop_wait(self) -> Optional[EventItem]:
        with self._cond:
            while True:
                if self._closed:
                    return None
                if len(self._queue) > 0:
                    item: EventItem = self._queue.popleft()
                    return item
                self._cond.wait()


class EventBus:
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
        ts_ns: int = time.time_ns()
        item: EventItem = EventItem(
            topic=topic,
            payload_obj=payload_obj,
            ts_ns=ts_ns,
            source=source,
        )

        subs_snapshot: List[_Subscriber] = []
        with self._lock:
            subs_snapshot = list(self._subscribers)

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
        sub: _Subscriber = _Subscriber(
            topic=topic,
            once=once,
            source=source,
        )

        with self._lock:
            self._subscribers.append(sub)

        try:
            while True:
                if cancel_event is not None:
                    if cancel_event.is_set():
                        break

                item = sub.pop_wait()
                if item is None:
                    break

                yield item

                if sub.once:
                    break

        finally:
            sub.close()
            with self._lock:
                new_list: List[_Subscriber] = []
                for s in self._subscribers:
                    if s is sub:
                        continue
                    new_list.append(s)
                self._subscribers = new_list
