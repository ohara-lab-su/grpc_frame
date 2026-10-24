"""Local control class. No gRPC dependencies."""
from __future__ import annotations
from pathlib import Path
from typing import Any


class SimpleCtrl:
    def __init__(self) -> None:
        self._value: float = 0.0

    def set_value(self, value: float) -> None:
        self._value = float(value)

    def get_value(self) -> float:
        return self._value

    def status(self) -> dict[str, Any]:
        return {"value": self._value, "ready": True}

    def save_on_server(self, filename: str) -> str:
        """Intentionally writes on the SERVER machine."""
        target = Path(filename)
        target.write_text(str(self._value) + "\n", encoding="utf-8")
        return str(target)
