"""Application-facing client: remote calls plus client-local behavior."""
from __future__ import annotations
from pathlib import Path
from grpc_frame.grpc_client import SyncGrpcClient


class SimpleClient(SyncGrpcClient):
    def __init__(self, server_ip: str, server_port: int) -> None:
        super().__init__(server_ip=server_ip, server_port=server_port)
        # Describe creates an instance method for every remote public method.
        # Rebind *after* super().__init__ to override a remote method name.
        self.save_on_server = self._save_on_client_override

    def save_on_client(self, filename: str) -> Path:
        """Fetch server state, then save on the client filesystem."""
        value: float = self.get_value()
        target = Path(filename)
        target.write_text(f"{value}\n", encoding="utf-8")
        return target

    def _save_on_client_override(self, filename: str) -> Path:
        return self.save_on_client(filename)
