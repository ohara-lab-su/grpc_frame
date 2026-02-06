#!/usr/bin/env python3
"""
step 型の 呼び出し
GUI 上で独立ループから呼び出す(mainスレッドとJoyPadスレッドを一緒にするため)

mac などでjoygame などのオブジェクトを main スレッド以外で使うとハマる問題(SDL問題)
の回避で、start/stop がたから、while: step 形に変更

Kengo NAKADA
kengo.nakada@mat.shimane-u.ac.jp
kengo.nakada@gmail.com
"""
from typing import Any, Dict, List, Optional, Union, Tuple, Callable, Sequence
import time
import grpc

from cobotta2.server import JoyPadClient, joypad_pb2, joypad_pb2_grpc
from cobotta2.pad import InputJoyPadGrpcClient

from x_logger import XLogger


def main() -> None:
    logger = XLogger()
    logger.info("[CLIENT] JoyPad gRPC client main start")

    client = JoyPadClient(
        server_ip="10.170.10.38",
        server_port=50051,
        logger=logger,
    )

    if not client.is_connected():
        logger.error("[CLIENT] gRPC connection failed")
        return

    logger.info("[CLIENT] connected")

    # ============================================================
    # ctrl は local / server / client 共通の公開 API（client 側は proxy）
    # ============================================================

    # ============================================================
    # client responsibility（ctrl main と同じ並び）
    # ============================================================
    client.reset_error()
    client.motor_on()
    client.take_arm()

    # ============================================================
    # runtime start（実体は server 側 runtime を動かす要求）
    # サーバ側でのrobottoに送るためのループ
    # local起動だと同じマシン(client)でこれを行う
    # ============================================================
    logger.info("[CLIENT] runtime started (requested)")
    client.runtime_set_scale(10.0)
    client.runtime_start()

    # ============================================================
    # input push（client 側の固有責務）
    # joypad 読み込み側のループ inverval 設定
    # ============================================================
    logger.info("[CLIENT] input started (requested)")
    input_pad = InputJoyPadGrpcClient(
        grpc_client=client,
        interval=0.02,
        logger=logger,
    )

    # input_pad.start()
    # try:
    #     while True:
    #         time.sleep(0.02)

    try:
        while True:
            input_pad.step()
            time.sleep(0.02)  # 外側で周期制御

    except KeyboardInterrupt:
        logger.info("[CLIENT] interrupted")

    finally:
        logger.info("[CLIENT] stopping input loop")

        logger.info("[CLIENT] stopping joypad(server)")
        client.joypad_stop()
        client.give_arm()
        client.motor_off()
        logger.info("[CLIENT] JoyPad gRPC client main end")


if __name__ == "__main__":
    main()
