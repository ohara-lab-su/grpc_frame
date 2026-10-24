# Tutorial

[![en](https://img.shields.io/badge/lang-en-red.svg)](https://ohara-lab-su.github.io/grpc_frame/en/tutorials/grpc_intro.html) [![ja](https://img.shields.io/badge/lang-ja-yellow.svg)](https://ohara-lab-su.github.io/grpc_frame/ja/tutorials/grpc_intro.html)

This tutorial demonstrates how to use `grpc_frame` step by step.

We use a minimal example control class and demonstrate how a client can interact with the control class hosted on the server.

## Prepare a control class for the server

```python
#!/usr/bin/env python
from typing import Any, Dict, List, Optional, Tuple


class SimpleCtrl:
    """
    Minimal control class for framework testing
    - Used to verify argument and return-value patterns
    """

    def __init__(
        self,
        name: str = "simple",
        logger: Optional[Any] = None,
    ):
        self._name = name
        self._counter = 0
        self._logger = logger

    # Property
    @property
    def name(self) -> str:
        return self._name

    # Returns str
    def ping(self) -> str:
        return "pong"

    # Two arguments -> int
    def add(self, a: int, b: int) -> int:
        return a + b

    # One argument -> str
    def echo(self, msg: str) -> str:
        return msg

    # list -> float
    def sum_list(
        self,
        values: List[float],
    ) -> float:
        return float(sum(values))

    # Mixed keyword arguments -> dict
    def mix(
        self,
        a: int,
        b: int = 1,
        *,
        scale: float = 1.0,
        tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        val = (a + b) * scale
        return {"value": val, "tag": tag}

    # Tuple return value
    def make_tuple(
        self,
        a: int,
        b: str,
    ) -> Tuple[int, str]:
        return (a, b)

    # Dictionary return value
    def make_dict(self, key: str, value: Any) -> Dict[str, Any]:
        return {key: value}

    # Optional -> Optional
    def maybe(
        self,
        x: Optional[int] = None,
    ) -> Optional[int]:
        return x

    # Returns None
    def set_name(
        self,
        name: str,
    ) -> None:
        self._name = name

    # Retrieve state
    def get_state(self) -> Dict[str, Any]:
        self._counter += 1
        return {"name": self._name, "counter": self._counter}

    # General arguments (*args, **kwargs)
    def general(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return {"args": list(args), "kwargs": dict(kwargs)}

```

## Attach the control class to the server and start it

Currently, `grpc_frame` implements a fully transparent proxy that exposes the server-side device-control class to the client. Unlike `ese774_frame`, it does not require selecting individual interfaces from the control class.

Prepare the following server startup script.
```python
#!/usr/bin/env python3
from __future__ import annotations

import time
from concurrent import futures
from typing import Any, Optional

import grpc
from grpc import channel_ready_future

import grpc_frame.ctrl_pb2_grpc as ctrl_pb2_grpc
from grpc_frame.grpc_server import _ControlServicer
from x_logger import XLogger

######################################
# --- Device Class ---
from simple_ctrl import SimpleCtrl
######################################

def simple_server(
    grpc_host: str,
    grpc_port: int,
    interval: float = 0.01,
    logger: Optional[Any] = None,
    log_level: Optional[str] = None,
) -> None:
    """ """
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
    )

    bind_addr: str = f"{grpc_host}:{grpc_port}"
    ret: int = server.add_insecure_port(bind_addr)
    if ret == 0:
        raise RuntimeError(f"bind failed: {bind_addr}")

    logger.info(f"gRPC bind OK: {bind_addr}")
    
    server.start()

    # # self-check（旧版と同一）
    ch = grpc.insecure_channel(bind_addr)
    channel_ready_future(ch).result(timeout=2.0)
    logger.info("gRPC self-check OK")

    #######################
    ctrl = SimpleCtrl()
    #######################

    servicer = _ControlServicer(
        ctrl_obj=ctrl,
        logger=logger,
        log_level=log_level,
    )

    ctrl_pb2_grpc.add_ControlServicer_to_server(
        servicer,
        server,
    )

    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt")

    finally:
        server.stop(grace=None)
        logger.info("gRPC server stopped")

        
if __name__ == "__main__":
    GRPC_HOST = "localhost"
    GRPC_PORT = 50051
    INTERVAL = 0.01
    LOG_LEVEL = "INFO"

    logger_ = XLogger(
        log_level=LOG_LEVEL,
        logger_name="SimpleCtrl",
    )

    simple_server(
        grpc_host=GRPC_HOST,
        grpc_port=GRPC_PORT,
        interval=INTERVAL,
        logger=logger_,
        log_level=LOG_LEVEL,
    )
```

## Create a client class by inheriting from Frame

## Write the client-side control program

---
## Author
- Kengo NAKADA