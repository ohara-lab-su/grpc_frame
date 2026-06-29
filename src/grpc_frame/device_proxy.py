#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""DeviceProxy support for grpc_frame.

This module provides the same entry/register API as
``ese774_frame.clients.device_proxy`` while constructing gRPC clients.

The public entry points are intentionally kept compatible:

- DeviceProxyEntry
- register_device_proxy(...)
- unregister_device_proxy(...)
- get_device_proxy_entry(...)
- list_device_proxies()
- DeviceProxy(...)
- create_device_proxy(...)

A device package can register direct client classes, for example
``SyncPixetGrpcClient`` and ``AsyncPixetGrpcClient``.  If direct client
classes are not registered, DeviceProxy falls back to the generic
``SyncGrpcClient`` / ``AsyncGrpcClient`` classes.
"""

from typing import Any, Dict, List, Optional, Type

from grpc_frame.grpc_client import AsyncGrpcClient
from grpc_frame.grpc_client import SyncGrpcClient


class DeviceProxyEntry(object):
    """DeviceProxy registration entry.

    The field names are kept compatible with ese774_frame.
    ``api_spec`` and ``object_name`` are retained as metadata for API
    compatibility and pyi generation.  grpc_frame itself obtains callable
    methods from Describe RPC, so these fields are not required for runtime
    method binding.
    """

    def __init__(
        self,
        device_class: str,
        async_client_cls: Optional[Type[Any]] = None,
        sync_client_cls: Optional[Type[Any]] = None,
        api_spec: Optional[list] = None,
        object_name: Optional[str] = None,
        default_async_mode: bool = True,
    ) -> None:
        self.device_class = device_class
        self.async_client_cls = async_client_cls
        self.sync_client_cls = sync_client_cls
        self.api_spec = api_spec
        self.object_name = object_name
        self.default_async_mode = default_async_mode


_DEVICE_PROXY_REGISTRY: Dict[str, DeviceProxyEntry] = {}


def register_device_proxy(
    device_class: str,
    *,
    async_client_cls: Optional[Type[Any]] = None,
    sync_client_cls: Optional[Type[Any]] = None,
    api_spec: Optional[list] = None,
    object_name: Optional[str] = None,
    default_async_mode: bool = True,
    aliases: Optional[List[str]] = None,
) -> None:
    """Register a device class for DeviceProxy.

    This signature is compatible with ese774_frame.  For grpc_frame,
    direct client classes are the normal registration target:

    ``register_device_proxy("MiniPixCtrl", async_client_cls=..., sync_client_cls=...)``

    ``api_spec`` is accepted for compatibility and pyi tooling, but runtime
    methods are resolved by the gRPC Describe RPC.
    """
    if not device_class:
        raise ValueError("device_class is required")

    if async_client_cls is None and sync_client_cls is None and api_spec is None:
        raise ValueError("async_client_cls, sync_client_cls, or api_spec is required")

    entry = DeviceProxyEntry(
        device_class=device_class,
        async_client_cls=async_client_cls,
        sync_client_cls=sync_client_cls,
        api_spec=api_spec,
        object_name=object_name,
        default_async_mode=default_async_mode,
    )

    names = [device_class]
    if aliases:
        names.extend(aliases)

    for name in names:
        _DEVICE_PROXY_REGISTRY[name] = entry


def unregister_device_proxy(device_class: str) -> None:
    """Unregister one DeviceProxy key.

    This follows the ese774_frame behavior: only the specified key is removed.
    If aliases were registered, remove each alias explicitly when needed.
    """
    _DEVICE_PROXY_REGISTRY.pop(device_class, None)


def get_device_proxy_entry(device_class: str) -> DeviceProxyEntry:
    """Return a registered DeviceProxyEntry."""
    if device_class not in _DEVICE_PROXY_REGISTRY:
        raise KeyError(
            f"DeviceProxy is not registered: {device_class}. "
            "Call register_device_proxy(...) first."
        )
    return _DEVICE_PROXY_REGISTRY[device_class]


def list_device_proxies() -> List[str]:
    """Return registered DeviceProxy keys."""
    return sorted(_DEVICE_PROXY_REGISTRY.keys())


def DeviceProxy(
    device_class: str,
    *args,
    async_mode: Optional[bool] = None,
    **kwargs,
) -> Any:
    """Create a client instance from a registered device_class.

    Args:
        device_class: Registered device class name or alias.
        *args: Forwarded to the selected client class.
        async_mode: True for async client, False for sync client, None to use
            the registration default.
        **kwargs: Forwarded to the selected client class.

    Returns:
        Async or sync client instance.
    """
    entry = get_device_proxy_entry(device_class)

    if async_mode is None:
        async_mode = entry.default_async_mode

    if async_mode:
        client_cls = entry.async_client_cls or AsyncGrpcClient
        return client_cls(*args, **kwargs)

    client_cls = entry.sync_client_cls or SyncGrpcClient
    return client_cls(*args, **kwargs)


def create_device_proxy(device_class: str):
    """Create a DeviceProxy factory with fixed device_class.

    This helper is compatible with ese774_frame and is useful for generating
    package-local entry functions/classes that preserve IDE completion through
    generated pyi files.
    """

    def proxy(
        *args,
        async_mode: Optional[bool] = None,
        **kwargs,
    ) -> Any:
        return DeviceProxy(
            device_class,
            *args,
            async_mode=async_mode,
            **kwargs,
        )

    return proxy
