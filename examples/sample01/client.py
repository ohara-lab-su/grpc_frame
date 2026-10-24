"""Run this in a second terminal after starting the server."""
from __future__ import annotations
from server_grpc.client import SimpleClient

HOST: str = "127.0.0.1"
PORT: int = 50051


def main() -> None:
    client = SimpleClient(server_ip=HOST, server_port=PORT)
    try:
        client.set_value(12.5)  # remote
        print(client.get_value())  # remote
        print(client.status())  # remote
        print(client.save_on_client("client_value.txt"))  # local
        print(client.save_on_server("also_client_value.txt"))  # overridden local
        print(client._raw_save_on_server("server_value.txt"))  # original remote
    finally:
        client.close()


if __name__ == "__main__":
    main()
