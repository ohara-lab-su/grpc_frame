# gRPC Frame

[![en](https://img.shields.io/badge/lang-en-red.svg)](https://github.com/ohara-lab-su/grpc_frame/blob/main/README.en.md)
[![ja](https://img.shields.io/badge/lang-ja-yellow.svg)](https://github.com/ohara-lab-su/grpc_frame/blob/main/README.md)

gRPC Frame is a communication framework for exposing Python control
classes over gRPC.

Its central design concept is a **transparent proxy**. Public methods of
a server-side control object are discovered automatically and
dynamically bound to the client as Python methods. For ordinary unary
calls, this removes the need to define a dedicated protobuf message and
RPC method for every control method.

The framework is intended for device control, experimental instruments,
measurement servers, laboratory automation, and similar systems where an
existing Python control class should be accessible over the network with
nearly the same calling style as a local object.

> gRPC Frame exposes **public callables** of the control object.
> Properties are intentionally excluded from discovery to avoid side
> effects during introspection.

------------------------------------------------------------------------

## Features

-   Automatic discovery of server-side public methods through the
    `Describe` RPC
-   Dynamic binding of remote methods on the client
-   Generic transport of Python `*args` and `**kwargs`
-   Standard unary calls plus server-streaming `StreamCall`
-   Topic-based event subscription
-   JSON-first serialization with pickle fallback
-   JSON handling for `bytes`, `bytearray`, and `tuple`
-   Synchronous client and an asynchronous wrapper
-   DeviceProxy registry for constructing clients from device-class
    names
-   Low-level gRPC API usage without depending on generated Stub classes
    for client dispatch

------------------------------------------------------------------------

## Architecture

A normal method call follows this conceptual path:

``` text
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

When a client connects, it calls `Control/Describe`. The returned method
names and signatures are used to create `self.<method_name>`
dynamically.

For example, if the server-side control class contains:

``` python
class SimpleCtrl:
    def ping(self) -> str:
        return "pong"

    def add(self, a: int, b: int) -> int:
        return a + b
```

the client can conceptually use:

``` python
client.ping()
client.add(10, 20)
```

Instead of adding dedicated protobuf RPCs for `ping` and `add`, both
calls are transported through the generic `Call` RPC with a method name,
positional arguments, and keyword arguments.

------------------------------------------------------------------------

## RPC interface

### Control service

`ctrl.proto` defines three RPCs:

``` proto
service Control {
  rpc Describe(Empty) returns (MethodTable);
  rpc Call(DispatchRequest) returns (DispatchResponse);
  rpc StreamCall(DispatchRequest) returns (stream DispatchResponse);
}
```

### `Describe`

`Describe` returns the callable methods that the server exposes.

For each method, it reports:

-   method name
-   signature string obtained from `inspect.signature()`

Only public callables are included. Members whose names begin with `_`
are excluded. Properties are also excluded using static inspection
because evaluating a property during discovery may trigger side effects
such as COM operations, device access, or other I/O.

### `Call`

`Call` is the generic one-request/one-response method invocation RPC.

``` proto
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

The client serializes Python positional and keyword arguments into byte
payloads and sends them with the target method name. A successful
response is deserialized back into a Python object. If the server
returns an error, the client raises `RuntimeError`.

### `StreamCall`

`StreamCall` is a server-streaming variant in which one request can
produce multiple responses.

The client exposes it explicitly:

``` python
for value in client.stream_call("method_name", arg1, arg2):
    print(value)
```

This is a lower-level API independent of the normal `Describe` → dynamic
binding → `Call` path.

------------------------------------------------------------------------

## Event communication

gRPC Frame also supports event subscription through server-side
streaming.

`events.proto` defines:

``` proto
service Events {
  rpc Subscribe(SubscribeRequest) returns (stream Event);
}
```

A subscription request contains:

-   `topic`: topic to subscribe to
-   `once`: whether to stop after one event
-   `source`: event-source information

Client example:

``` python
for payload in client.subscribe(topic="status"):
    print(payload)
```

To receive only one event:

``` python
for payload in client.subscribe(topic="status", once=True):
    print(payload)
```

The internal `EventBus` is a lightweight in-process publish/subscribe
mechanism. It maintains subscriber queues and uses `threading.Condition`
to coordinate publishers and subscribers.

In the current `EventBus` implementation, `source` is stored as part of
the subscription state but is not yet applied as a publish-time source
filter. It is retained for future extension.

------------------------------------------------------------------------

## Serialization

Arguments, return values, and event payloads are handled by `adapter`.

The serialization policy is **JSON first + pickle fallback**:

1.  Attempt JSON serialization.
2.  If the object cannot be represented as JSON, fall back to pickle.

The first byte of each payload identifies the format:

  Prefix   Format
  -------- --------
  `b"J"`   JSON
  `b"P"`   pickle

### Additional JSON handling

The adapter preserves several Python types that plain JSON cannot
represent directly:

-   `bytes` / `bytearray`: encoded as Base64
-   `tuple`: represented with a dedicated marker and restored as a tuple
    during decoding

This allows common dict/list/string/numeric/boolean/`None` data, binary
payloads, and tuples to remain on the JSON path where possible.

### Security note for pickle

pickle can represent a wide range of Python objects, but it is not
suitable for deserializing untrusted input. If gRPC Frame is exposed
beyond a trusted network, the pickle fallback and the current non-TLS
channel model must be considered explicitly. Network isolation,
authentication, TLS, and a restricted serialization policy may be
required.

------------------------------------------------------------------------

## Client API

### `GrpcClient`

`GrpcClient` is the base generic client.

``` python
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

Initialization performs the following steps:

1.  Create a channel with `grpc.insecure_channel()`.
2.  Wait for the gRPC server to become ready.
3.  Call the `Describe` RPC.
4.  Receive the remote method table.
5.  Build a dispatcher for each method.
6.  Register each dispatcher as `self.<method_name>` and
    `_raw_<method_name>`.

`is_connected()` checks whether a real `Describe` RPC succeeds rather
than only inspecting local channel state.

### gRPC options

`GrpcClient` accepts `grpc_options`. This is useful when transferring
large images or other binary payloads.

``` python
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

Corresponding server-side limits must also be configured when required.

### `SyncGrpcClient`

`SyncGrpcClient` provides the synchronous interface. Dynamically
discovered methods behave as normal blocking Python calls.

``` python
from grpc_frame.grpc_client import SyncGrpcClient

client = SyncGrpcClient(
    server_ip="127.0.0.1",
    server_port=50051,
)

value = client.ping()
```

### `AsyncGrpcClient`

`AsyncGrpcClient` wraps methods discovered by `Describe` as async
methods.

``` python
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

The current implementation is not based on native `grpc.aio` calls. It
runs the synchronous remote method through the event loop executor.

------------------------------------------------------------------------

## DeviceProxy

`device_proxy.py` provides a registry that maps a device-class name to
client classes and creates a client instance from that name.

The public API includes:

``` text
DeviceProxyEntry
register_device_proxy(...)
unregister_device_proxy(...)
get_device_proxy_entry(...)
list_device_proxies()
DeviceProxy(...)
create_device_proxy(...)
```

Registration example:

``` python
from grpc_frame.device_proxy import register_device_proxy

register_device_proxy(
    "MyDeviceCtrl",
    sync_client_cls=MySyncClient,
    async_client_cls=MyAsyncClient,
    aliases=["my_device"],
)
```

Client creation:

``` python
from grpc_frame.device_proxy import DeviceProxy

client = DeviceProxy(
    "MyDeviceCtrl",
    "127.0.0.1",
    50051,
    async_mode=False,
)
```

If a direct client class is not registered, DeviceProxy can fall back to
the generic `SyncGrpcClient` or `AsyncGrpcClient`.

`api_spec` and `object_name` are retained as compatibility/tooling
metadata. Runtime method discovery in gRPC Frame itself is performed by
the `Describe` RPC.

------------------------------------------------------------------------

## Designing a control class

A control object can be implemented as an ordinary Python class.

``` python
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

In this example, `ping`, `add`, `echo`, `sum_list`, `mix`, `make_tuple`,
and `get_state` are discoverable public callables.

The `name` property is not exposed by `Describe`.

------------------------------------------------------------------------

## How much protobuf definition is required?

Adding an ordinary control method does not require a new protobuf RPC
for that method.

For example, after adding:

``` python
def reset(self) -> None:
    ...
```

to the server-side control object, `Describe` can discover `reset`, and
a newly connected client can bind `reset()` dynamically.

The normal workflow is therefore:

``` text
add a public method to the ctrl class
        |
        v
Describe discovers it
        |
        v
the client binds it dynamically
        |
        v
the generic Call RPC executes it
```

A protobuf change is required when the communication pattern itself
changes---for example, when adding a fundamentally different streaming
service or a new explicit message contract.

------------------------------------------------------------------------

## Relationship to `ese774_frame`

gRPC Frame shares the goal of making a server-side control object easy
to use from a client.

For ordinary method calls, gRPC Frame emphasizes transparent discovery
and generic dispatch through `Describe` and `Call`, rather than
requiring a separate API schema for every control method.

`device_proxy.py` also intentionally preserves an entry/register API
compatible with `ese774_frame.clients.device_proxy`.

------------------------------------------------------------------------

## Operational considerations

### Public methods become remote API

Public callables on the control object are discovery candidates.
Internal server methods should not be left public unintentionally.
Methods that must not become remote API should use private/internal
names beginning with `_`.

### Properties are not remote methods

Properties are explicitly excluded from discovery. This prevents
introspection from accidentally triggering device I/O, COM access, or
other side effects.

Values that must be queried remotely are better exposed as explicit
methods such as `get_status()`.

### Network security

The current client uses `grpc.insecure_channel()`. For deployments
outside a closed experimental network, TLS, authentication,
authorization, and network access control should be designed separately.

### API compatibility

Dynamic binding makes it easy to add server methods, but renaming
methods or changing arguments and return values can still break client
programs. A versioning policy is recommended when the framework is used
as a stable device-control API.

------------------------------------------------------------------------

## Documentation

The Sphinx documentation contains the tutorial and API reference:

``` text
api/modules
tutorials/grpc_intro
```

Repository:

https://github.com/ohara-lab-su/grpc_frame/

------------------------------------------------------------------------

## Author

Kengo NAKADA
