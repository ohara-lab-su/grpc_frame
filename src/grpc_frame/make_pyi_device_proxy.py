#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Generate pyi declarations for grpc_frame DeviceProxy.

The function signature is kept compatible with
``ese774_frame.clients.make_pyi_device_proxy.make_pyi_device_proxy``.
"""

from pathlib import Path
from typing import List, Optional


def make_pyi_device_proxy(
    filename: str,
    import_lines: List[str],
    device_class: str,
    sync_client_class_name: str,
    async_client_class_name: str,
    aliases: Optional[List[str]] = None,
    all_names: Optional[List[str]] = None,
) -> None:
    """Generate a pyi file for DeviceProxy overloads.

    Args:
        filename: Output pyi path.
        import_lines: Import lines written into the pyi file.
        device_class: Registered device class name.
        sync_client_class_name: Sync client class name returned when
            ``async_mode=False``.
        async_client_class_name: Async client class name returned when
            ``async_mode=True``.
        aliases: Device class aliases.
        all_names: Optional ``__all__`` contents.
    """
    names = [device_class]

    if aliases is not None:
        names.extend(aliases)

    lines = [
        "from typing import Any, Literal, Optional, overload",
        "",
    ]

    lines.extend(import_lines)
    lines.append("")

    for name in names:
        lines.extend(
            [
                "@overload",
                "def DeviceProxy(",
                '    device_class: Literal["%s"],' % name,
                "    *args: Any,",
                "    async_mode: Literal[False] = False,",
                "    **kwargs: Any,",
                ") -> %s: ..." % sync_client_class_name,
                "",
                "@overload",
                "def DeviceProxy(",
                '    device_class: Literal["%s"],' % name,
                "    *args: Any,",
                "    async_mode: Literal[True],",
                "    **kwargs: Any,",
                ") -> %s: ..." % async_client_class_name,
                "",
            ]
        )

    lines.extend(
        [
            "def DeviceProxy(",
            "    device_class: str,",
            "    *args: Any,",
            "    async_mode: Optional[bool] = None,",
            "    **kwargs: Any,",
            ") -> Any: ...",
            "",
        ]
    )

    if all_names is not None:
        lines.append("__all__ = [")
        for name in all_names:
            lines.append('    "%s",' % name)
        lines.append("]")
        lines.append("")

    Path(filename).write_text("\n".join(lines), encoding="utf-8")
