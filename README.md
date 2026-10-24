# gRPC Frame

[![en](https://img.shields.io/badge/lang-en-red.svg)](https://github.com/ohara-lab-su/grpc_frame/blob/main/README.md)
[![ja](https://img.shields.io/badge/lang-ja-yellow.svg)](https://github.com/ohara-lab-su/grpc_frame/blob/main/README.ja.md)

gRPC Frame is a communication framework for remotely accessing Python control classes over gRPC.

Its central concept is a **transparent proxy**. The framework automatically discovers the public methods of a control class (`ctrl` object) hosted on the server and dynamically exposes methods with the same names on the client. Consequently, ordinary unary RPC operations do not require a separate protobuf message or RPC definition for every control method.

It is intended for device control, experimental instruments, measurement servers, laboratory automation, and other applications that need to invoke an existing Python control class across a network using almost the same interface as a local object.

> gRPC Frame discovers **public callables** on the control object. Properties are excluded to avoid side effects during discovery.

---

## Features

- Automatic discovery of server-side public methods through the `Describe` RPC
- Dynamic binding of remote methods on the client
- Generic RPC dispatch of `*args` and `**kwargs`
- Server-streaming `StreamCall` in addition to ordinary unary calls
- Topic-based event subscriptions
- JSON-first serialization with pickle fallback for objects that cannot be encoded as JSON
- Preservation of `bytes`, `bytearray`, and `tuple` through the JSON encoding path
- Synchronous clients and an asynchronous wrapper
- A DeviceProxy registry for constructing clients by device class name
- RPC construction through the low-level gRPC API without depending on generated protobuf stubs

---

## Architecture

An ordinary method call follows this conceptual path:

```text
[ Python client ]
        |
        |  method(*args, **kwargs)
        v
[ GrpcClient dynamic dispatcher ]
        |
        |  adapter.pack_args / pack_kwargs
        v
[ DispatchRequest ]
        |
        |  gRPC
        v
[ Control service ]
        |
        |  unpack args / kwargs
        v
[ ctrl object (pure Python) ]
        |
        |  return value
        v
[ DispatchResponse ]
        |
        |  adapter.unpack_result
        v
[ Python client ]
```

On connection, the client calls `Control/Describe`. Based on the method names and signatures returned by the server, it dynamically creates `self.<method_name>` methods.

For example, suppose the server-side control class provides:

```python
class SimpleCtrl:
    def ping(self) -> str:
        return "pong"

    def add(self, a: int, b: int) -> int:
        return a + b
```

The client can then call:

```python
client.ping()
client.add(10, 20)
```

Instead of adding a dedicated protobuf RPC for each method, the shared `Call` RPC carries the method name, positional arguments, and keyword arguments and dispatches the call to the corresponding server-side method.

---

## RPC interface

### Control service

`ctrl.proto` defines three RPC operations:

```proto
service Control {
  rpc Describe(Empty) returns (MethodTable);
  rpc Call(DispatchRequest) returns (DispatchResponse);
  rpc StreamCall(DispatchRequest) returns (stream DispatchResponse);
}
```

### `Describe`

Retrieves the server-side methods eligible for discovery. For each method, it returns:

- The method name
- A signature string obtained from `inspect.signature()`

Discovery includes public callables and excludes names beginning with `_`. Properties are detected statically and excluded because evaluating them could trigger COM operations, device access, or other side effects.

### `Call`

A generic request/response operation with one request and one response:

```proto
message DispatchRequest {
  string method = 1;
  bytes args = 2;
  bytes kwargs = 3;
}

message DispatchResponse {
  bool ok = 1;
  bytes result = 2;
  string error = 3;
}
```

The client serializes Python positional and keyword arguments into `bytes` and sends them with the method name. On success, it reconstructs the returned Python object. If the server reports an error, the client raises `RuntimeError`.

### `StreamCall`

A server-streaming RPC that returns multiple responses for a single request. Invoke it explicitly:

```python
for value in client.stream_call("method_name", arg1, arg2):
    print(value)
```

This is a separate, lower-level API; it is not the ordinary `Describe` → dynamic binding → `Call` path.

---

## Event communication

gRPC Frame also provides event subscriptions implemented with server-side streaming. `events.proto` defines:

```proto
service Events {
  rpc Subscribe(SubscribeRequest) returns (stream Event);
}
```

A subscription request can specify:

- `topic`: the topic to subscribe to
- `once`: whether to stop after receiving one event
- `source`: identifying information for the event source

For example:

```python
for payload in client.subscribe(topic="status"):
    print(payload)
```

To receive only one event:

```python
for payload in client.subscribe(topic="status", once=True):
    print(payload)
```

The internal `EventBus` is a lightweight, in-process publish/subscribe mechanism. It maintains subscriber queues by topic and synchronizes publishing and subscription with `threading.Condition`.

In the current `EventBus` implementation, `source` is retained in the subscription state but is **not yet used to filter events by source** when publishing. It is reserved for possible future extension.

---

## Serialization

The `adapter` module handles conversion of arguments, return values, and event payloads. Its policy is **JSON first, pickle fallback**:

1. Attempt JSON serialization.
2. Fall back to pickle if the object cannot be serialized as JSON.

The first byte of a payload identifies the format:

| Prefix | Format |
| --- | --- |
| `b"J"` | JSON |
| `b"P"` | pickle |

### Additional JSON type support

The adapter preserves certain types that standard JSON does not represent directly:

- `bytes` / `bytearray`: encoded using Base64
- `tuple`: encoded with a dedicated marker to distinguish it from a list, then reconstructed as a tuple

Thus, the JSON path supports ordinary `dict`, `list`, `str`, `int`, `float`, `bool`, and `None`, as well as binary data and tuples.

### Security considerations for pickle fallback

Pickle supports a broad range of Python objects, but deserializing untrusted pickle data is unsafe. If gRPC Frame is exposed to an untrusted network, consider both its current serialization model, including pickle, and its non-TLS channel. Network isolation, authentication, TLS, and serialization restrictions must be designed separately as appropriate.

---

## Clients

### `GrpcClient`

The basic client:

```python
from grpc_frame.grpc_client import GrpcClient

client = GrpcClient(
    server_ip="127.0.0.1",
    server_port=50051,
    timeout_sec=5.0,
)

print(client.is_connected())

result = client.add(10, 20)
print(result)

client.close()
```

Initialization performs the following operations:

1. Create a channel with `grpc.insecure_channel()`.
2. Wait until the gRPC server is ready.
3. Execute the `Describe` RPC.
4. Retrieve the method table.
5. Create a dispatcher for each remote method.
6. Register it as `self.<method_name>` and `_raw_<method_name>`.

`is_connected()` checks connectivity by verifying that the `Describe` RPC actually succeeds.

### gRPC options

`GrpcClient` accepts `grpc_options`. However, in the current implementation supplied for review, `SyncGrpcClient` and `AsyncGrpcClient` do **not** forward the received `grpc_options` argument to their base class. The following configuration is therefore effective **when using `GrpcClient` directly**.

For large images or binary payloads, for example, gRPC message-size options can be specified:

```python
options = (
    ("grpc.max_receive_message_length", 32 * 1024 * 1024),
    ("grpc.max_send_message_length", 32 * 1024 * 1024),
)

client = GrpcClient(
    server_ip="127.0.0.1",
    server_port=50051,
    grpc_options=options,
)
```

Corresponding server-side settings are also required.

### `SyncGrpcClient`

A synchronous client whose remote methods are invoked as ordinary functions:

```python
from grpc_frame.grpc_client import SyncGrpcClient

client = SyncGrpcClient(
    server_ip="127.0.0.1",
    server_port=50051,
)

value = client.ping()
```

### `AsyncGrpcClient`

Wraps the remote methods discovered by `Describe` as asynchronous methods:

```python
import asyncio
from grpc_frame.grpc_client import AsyncGrpcClient


async def main() -> None:
    client = AsyncGrpcClient(
        server_ip="127.0.0.1",
        server_port=50051,
    )

    value = await client.ping()
    print(value)
    client.close()


asyncio.run(main())
```

The current implementation is **not** a native asynchronous RPC client using `grpc.aio`. It is a wrapper that executes synchronous remote methods in an event-loop executor.

---

## DeviceProxy

`device_proxy.py` provides a registry that associates device class names with client classes and constructs client instances by name.

Its main APIs are:

```text
DeviceProxyEntry
register_device_proxy(...)
unregister_device_proxy(...)
get_device_proxy_entry(...)
list_device_proxies()
DeviceProxy(...)
create_device_proxy(...)
```

Registration example:

```python
from grpc_frame.device_proxy import register_device_proxy

register_device_proxy(
    "MyDeviceCtrl",
    sync_client_cls=MySyncClient,
    async_client_cls=MyAsyncClient,
    aliases=["my_device"],
)
```

Construction example:

```python
from grpc_frame.device_proxy import DeviceProxy

client = DeviceProxy(
    "MyDeviceCtrl",
    "127.0.0.1",
    50051,
    async_mode=False,
)
```

When no dedicated client class has been registered, the framework can fall back to the generic `SyncGrpcClient` or `AsyncGrpcClient`.

`api_spec` and `object_name` are retained as metadata for compatibility and tooling. Runtime method discovery itself uses the `Describe` RPC.

---

## Designing a control class

A control class exposed through gRPC Frame can be an ordinary Python class:

```python
from typing import Any, Dict, List, Optional, Tuple


class SimpleCtrl:
    def __init__(self, name: str = "simple") -> None:
        self._name = name
        self._counter = 0

    @property
    def name(self) -> str:
        return self._name

    def ping(self) -> str:
        return "pong"

    def add(self, a: int, b: int) -> int:
        return a + b

    def echo(self, msg: str) -> str:
        return msg

    def sum_list(self, values: List[float]) -> float:
        return float(sum(values))

    def mix(
        self,
        a: int,
        b: int = 1,
        *,
        scale: float = 1.0,
        tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        value = (a + b) * scale
        return {"value": value, "tag": tag}

    def make_tuple(self, a: int, b: str) -> Tuple[int, str]:
        return (a, b)

    def get_state(self) -> Dict[str, Any]:
        self._counter += 1
        return {
            "name": self._name,
            "counter": self._counter,
        }
```

Here, `ping`, `add`, `echo`, `sum_list`, `mix`, `make_tuple`, and `get_state` are public callables and therefore eligible for discovery.

By contrast, `name` is a property and is not included among the methods returned by `Describe`.

---

## How much protobuf code is necessary?

Adding an ordinary control method does not require a separate protobuf RPC definition.

For example, add the following method to `SimpleCtrl`:

```python
def reset(self) -> None:
    ...
```

When the class is exposed as the server-side `ctrl_obj`, `Describe` detects `reset`, and the client dynamically gains `reset()` upon connection:

```text
Add a public method to the ctrl class
        |
        v
Describe discovers the method
        |
        v
The client binds it dynamically
        |
        v
The shared Call RPC invokes it
```

A protobuf extension is necessary when adding a different communication pattern, such as a new streaming service or another message contract.

---

## Client-side behavior overrides and file saving

`GrpcClient` and `SyncGrpcClient` use the server's `Describe` results to register remote methods as **instance attributes** through `setattr(self, name, dispatcher)`. Consequently, merely defining a method with the same name in a client subclass does not override the dynamically installed dispatcher: the instance attribute takes precedence during normal lookup.

To change behavior on the client, rebind the method **after** calling `super().__init__()`. The original remote dispatcher is preserved as `_raw_<method_name>`.

```python
from pathlib import Path
from grpc_frame.grpc_client import SyncGrpcClient


class FileClient(SyncGrpcClient):
    def __init__(self, server_ip: str, server_port: int) -> None:
        super().__init__(server_ip=server_ip, server_port=server_port)
        self.save_on_server = self._save_locally

    def _save_locally(self, filename: str) -> str:
        data = self.get_value()  # Retrieve data from the server.
        Path(filename).write_text(f"{data}\n", encoding="utf-8")
        return filename
```

Despite its name, `save_on_server()` in this example writes a file **on the client**. To invoke the original server-side method, use `client._raw_save_on_server(...)`.

A less ambiguous design is to provide a separate local method such as `save_on_client()`. Both approaches are illustrated in `example/server_grpc/client.py`.

---

## Relationship to `ese774_frame`

Like `ese774_frame`, gRPC Frame aims to make server-side control objects straightforward to operate from client programs.

gRPC Frame prioritizes transparency through `Describe` and generic dispatch over defining an individual API schema for each ordinary control method.

`device_proxy.py` also retains entry and registration APIs designed with compatibility with `ese774_frame.clients.device_proxy` in mind.

---

## Operational considerations

### Public methods become remote APIs

Public callables on the control object are eligible for discovery. Do not unintentionally expose methods intended only for server-side use. Name internal methods with a leading `_` to keep them out of automatic discovery.

**This naming convention is not access control.** The current server-side `Call` implementation directly evaluates `getattr(self._ctrl_obj, method_name)` without verifying that the requested name belongs to the `Describe` method table. A caller capable of sending arbitrary `DispatchRequest` messages therefore cannot be prevented from invoking internal methods merely by using underscore-prefixed names.

Where access control is required, implement server-side validation of permitted method names and appropriate network authentication and protection.

### Properties are not remote methods

Properties are explicitly excluded from discovery to avoid triggering side effects such as device I/O or COM access while enumerating methods.

Expose values that must be read remotely through explicit public methods such as `get_status()`.

### Network security

The current client uses `grpc.insecure_channel()`. Outside an isolated experimental network, consider TLS, authentication, access control, and other protective measures.

### API compatibility

Dynamic binding makes it easy to add server methods, but renaming existing methods or changing their arguments or return types can break client applications. A versioning policy is advisable for instrument-control APIs.

---

## Related documentation

The Sphinx documentation includes tutorials and an API reference:

```text
api/modules
tutorials/grpc_intro
```

Repository: https://github.com/ohara-lab-su/grpc_frame/

---

## Author

Kengo NAKADA
