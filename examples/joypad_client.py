#!/usr/bin/env python3
"""
Kengo NAKADA
kengo.nakada@mat.shimane-u.ac.jp
kengo.nakada@gmail.com
"""
from typing import Optional

from cobotta2.pad import JoyPadCtrl
from grpc_frame import GrpcClient
from cobotta2.server_grpc import joypad_pb2_grpc

from x_logger import XLogger


class JoyPadClient(GrpcClient):
    _ctrl_class = JoyPadCtrl
    _stub_class = joypad_pb2_grpc.JoyPadControlStub
    _client_log_title = "JoyPadClient (gRPC Client)"

    def __init__(
        self,
        server_ip: str,
        server_port: int,
        logger: Optional[XLogger] = None,
    ) -> None:
        super().__init__(
            server_ip=server_ip,
            server_port=server_port,
            logger=logger,
        )
