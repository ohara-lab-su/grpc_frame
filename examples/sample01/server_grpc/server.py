"""Run the local control class over grpc_frame."""
from __future__ import annotations
import logging
from grpc_frame.grpc_server import create_grpc_server
from simple_ctrl import SimpleCtrl

HOST: str = "127.0.0.1"
PORT: int = 50051


def main() -> None:
    logger = logging.getLogger("simple_server")
    server = create_grpc_server(ctrl_obj=SimpleCtrl(), logger=logger)
    address = f"{HOST}:{PORT}"
    if server.add_insecure_port(address) == 0:
        raise RuntimeError(f"Cannot bind {address}")
    server.start()
    print(f"Listening at {address}")
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(grace=0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
