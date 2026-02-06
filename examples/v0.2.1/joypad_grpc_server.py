#!/usr/bin/env python3
"""
Kengo NAKADA
kengo.nakada@mat.shimane-u.ac.jp
kengo.nakada@gmail.com
#!/usr/bin/env python3
"""
import time
from concurrent import futures
from typing import Optional

import grpc
from grpc import channel_ready_future


# --- gRPC / proto ---
from cobotta2.server_grpc import joypad_pb2
from cobotta2.server_grpc import joypad_pb2_grpc

# --- dynamic dispatch (既存・変更なし) ---
# from cobotta2.server_grpc.grpc_server import (
#     build_dynamic_servicer_class,
# )
from grpc_frame import build_dynamic_servicer_class

# --- joypad / robot side ---
# from cobotta2.pad.input_grpc_server import InputGrpcServer
# from cobotta2.pad.joypad_ctrl import JoyPadCtrl
from cobotta2.pad import InputGrpcServer, JoyPadCtrl

from x_logger import XLogger

# ============================================================
#  Servicer クラス の動的作成
# ============================================================
JoyPadControlServicer = build_dynamic_servicer_class(
    pb2=joypad_pb2,
    pb2_grpc=joypad_pb2_grpc,
    service_name="JoyPadControl",
)


# ============================================================
# Servicer クラス を用いた、Joyad_server の起動
# ============================================================
def joypad_server(
    bcap_host: str,
    bcap_port: int,
    grpc_host: str,
    grpc_port: int,
    interval: float = 0.01,
    logger: Optional[XLogger] = None,
) -> None:
    logger = logger if logger is not None else XLogger()

    # Input Device インスタンスの作成
    input_device = InputGrpcServer(logger=logger)

    # JoPadCtrl インスタンスの作成
    ctrl = JoyPadCtrl(
        input_device=input_device,
        bcap_host=bcap_host,
        bcap_port=bcap_port,
        interval=interval,
        logger=logger,
    )

    # servicer インスタンスの作成
    servicer = JoyPadControlServicer(
        ctrl=ctrl,
        logger=logger,
    )

    # gRPC server の作成
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
    )

    joypad_pb2_grpc.add_JoyPadControlServicer_to_server(
        servicer,
        server,
    )

    bind_addr = f"{grpc_host}:{grpc_port}"
    if server.add_insecure_port(bind_addr) == 0:
        raise RuntimeError(f"bind failed: {bind_addr}")

    logger.info(f"gRPC bind OK: {bind_addr}")

    try:
        server.start()

        ch = grpc.insecure_channel(bind_addr)
        channel_ready_future(ch).result(timeout=2.0)
        logger.info("gRPC self-check OK")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt")

    finally:
        server.stop(grace=None)
        logger.info("gRPC server stopped")


# ------------------------------------------------------------
# main
# ------------------------------------------------------------

if __name__ == "__main__":
    BCAP_HOST = "10.170.10.37"
    BCAP_PORT = 5007
    GRPC_HOST = "10.170.10.38"
    GRPC_PORT = 50051
    INTERVAL = 0.01

    joypad_server(
        BCAP_HOST,
        BCAP_PORT,
        GRPC_HOST,
        GRPC_PORT,
        INTERVAL,
    )
