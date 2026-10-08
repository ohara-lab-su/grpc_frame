# CHANGELOG

[![en](https://img.shields.io/badge/lang-en-red.svg)](https://github.com/ohara-lab-su/grpc_frame/blob/main/CHANGELOG.en.md)
[![ja](https://img.shields.io/badge/lang-ja-yellow.svg)](https://github.com/ohara-lab-su/grpc_frame/blob/main/CHANGELOG.md)

## v0.5.14, 2026-10-05, K.Nakada

- Updated README.

## v0.5.13, 2026-10-05, K.Nakada

- Updated TOML configuration.
- Added PyPI support.

## v0.5.12, 2026-10-05, K.Nakada

Reorganized the proto build and maintenance utilities in `grpc_frame`.

- Moved proto generation and cleanup scripts to `grpc_frame/util/`:
  - `build_proto.py`
  - `build_proto_ctrl.py`
  - `build_proto_events.py`
  - `clean_proto.py`
  - `clean_site_packages.py`

- Updated path handling for proto files and generated files following the utility relocation:
  - `ctrl.proto` / `events.proto` remain directly under `grpc_frame/`.
  - Generated `ctrl_pb2.py` / `ctrl_pb2_grpc.py` / `events_pb2.py` / `events_pb2_grpc.py` also remain directly under `grpc_frame/`.
  - Separated the location of the build utilities themselves from the proto input and generated-output locations.

- Updated imports in the individual proto build scripts:
  - `build_proto_ctrl.py` / `build_proto_events.py` now directly use `build_proto.py` in the same `util/` directory without importing through the `grpc_frame` package.
  - Individual proto builds can now run even when the pb2 files have not yet been generated.

### Directory structure

```text
grpc_frame/
├── ctrl.proto
├── events.proto
├── ctrl_pb2.py
├── ctrl_pb2_grpc.py
├── events_pb2.py
├── events_pb2_grpc.py
├── ...
└── util/
    ├── __init__.py
    ├── build_proto.py
    ├── build_proto_ctrl.py
    ├── build_proto_events.py
    ├── clean_proto.py
    └── clean_site_packages.py
```

The proto files and generated pb2 files remain in their previous locations because they are used directly by the main `grpc_frame` package. Only development and maintenance scripts such as build and cleanup utilities were separated into `util/`.

## v0.5.11, 2026-08-10, K.Nakada

Added a server-streaming RPC to the generic dispatch mechanism.

- Added `StreamCall` to the `Control` service in `ctrl.proto`:
  - `rpc StreamCall(DispatchRequest) returns (stream DispatchResponse);`
  - Existing `Call` remains unchanged as the standard unary RPC.
  - Existing `DispatchRequest` / `DispatchResponse` definitions are reused.

- Added `StreamCall` handling to `grpc_server.py` / `grpc_client.py`:
  - `Call`: standard generic dispatch that returns one result for one invocation.
  - `StreamCall`: generic server-streaming dispatch that returns multiple results sequentially for one invocation.
  - `grpc_frame` does not prescribe the type or purpose of streamed data.

### Design

The original `grpc_frame` design is based on the generic unary `Call` RPC, which transparently invokes Python methods on the device side.

This basic design remains unchanged. `StreamCall` was added so that gRPC's standard server-streaming RPC can be used with the same generic-dispatch concept.

```text
Call
    request
        ↓
    method(...)
        ↓
    result

StreamCall
    request
        ↓
    streaming method(...)
        ↓
    result
    result
    result
    ...
```

## v0.5.10, 2026-07-28, nakada

- After cobotta3/4 setup.

# v0.5.9, 2026.07.14, nakada

- Version delivered to the Yashiro laboratory.

## v0.5.8, (2026.07.09), K.Nakada

Added support for configuring gRPC options for large messages.

- Added support for passing arbitrary `grpc_options` when creating gRPC channels/servers:
  - Added the `grpc_options` argument to `grpc_frame.grpc_client.GrpcClient`.
  - Added the `grpc_options` argument to `grpc_frame.grpc_server.create_grpc_server()`.
  - Added the `grpc_options` argument to `grpc_frame.grpc_com.create_com_grpc_server()`.
- `grpc_options` are passed directly to `grpc.insecure_channel()` and `grpc.server()`.
- Added support for large `bytes` return values over unary RPC:
  - For example, BMP images or other data exceeding gRPC Python's default 4 MB limit.
  - Users can configure `grpc.max_receive_message_length` / `grpc.max_send_message_length`.
- The default remains backward-compatible; an empty tuple is used when `grpc_options` is not specified.
- COM-enabled servers can now use the same option configuration as normal servers:
  - `create_com_grpc_server()` transparently passes `grpc_options` to `create_grpc_server()`.

## v0.5.7, (2026.06.29), K.Nakada

Added DeviceProxy support.

- Added an entry API compatible with `ese774_frame`'s DeviceProxy:
  - `DeviceProxyEntry`
  - `register_device_proxy()`
  - `unregister_device_proxy()`
  - `get_device_proxy_entry()`
  - `list_device_proxies()`
  - `DeviceProxy()`
  - `create_device_proxy()`
- Added direct client-class registration and creation of client instances from a device-class name or alias.
- Added registration of synchronous/asynchronous client classes.
- Added `default_async_mode` to configure the default creation mode of `DeviceProxy()`.
- Added helpers for generating pyi files for DeviceProxy.
- Exported DeviceProxy-related APIs from `grpc_frame.__init__`.

## v0.5.6, (2026.04.30), K.Nakada

Readjusted `pyproject.toml`.

- Python 3.7
- Python 3.11.9
- Python 3.13.13

## v0.5.5, (2026.04.30), K.Nakada

- Fixed a `grpc_tools` issue under setuptools 82:
  - `build_proto.py`

## v0.5.4, K.nakada

Added Python 3.7 support (possibly still incomplete).

## v0.5.3, K.nakada

- Added Python 3.7 support for the min_pix detector.
- Downgraded gRPC for that purpose and switched the TOML configuration from the other version.

## v0.5.2, K nakada

- Final version before the business trip (2026.03.15).
- Documentation adjustments.

## v0.5.1, K nakada

Documentation adjustments.

## v0.5.0, (v0.4.10+fix), k nakada

Version addressing the COM threading issue (ORIN2-gRPC/FastAPI compatible version).

The changes from 0.4.10 were larger than expected, so a separate version number was assigned.

- Bug fix for problems encountered when using the production cobotta2 system through gRPC:
  - Fixed `_collect_public_method_names`.
  - Fixed `_collect_signatures`.

## v0.4.10, nakada

Discovered that exceptions were not being propagated correctly to the client.

- To address this, the raw exception message is sent first when an exception occurs.
- Threading issue:
  - Methods called on a COM instance were being executed in separate gRPC handler threads.
  - This turned out to be a major problem and was the primary cause of the exceptions.

### COM threading issue

Windows COM requires operations to remain in the appropriate COM/thread context. Accessing the same COM object from another thread is not valid unless COM is initialized appropriately for that thread.

gRPC handlers normally run in separate threads. In ordinary Python code this is often not a concern because threads share process memory, but COM has thread-affinity constraints.

The solution is therefore not to initialize COM only once in the control-side constructor. Instead, COM execution is isolated so that COM initialization and execution occur in a dedicated execution thread. Commands from different gRPC handler threads are queued and serialized through that thread.

With `grpc.server`, RPC handlers (`_ControlServicer.Describe/Call`) execute in worker threads managed by `ThreadPoolExecutor`. In contrast, the control instance created as `ctrl = ...` in `orin2_grpc_server.py` is constructed in the main server thread. Therefore, in the normal implementation where a raw control object is passed directly to `_ControlServicer`, a COM object created in the main thread is accessed from different handler threads, which breaks COM's threading requirements.

- The important point is that gRPC uses the server startup thread and worker threads.

```text
gRPC Client
    ↓
grpc_server._ControlServicer (gRPC worker thread)
    ↓
ThreadSafeCtrlProxy
    ↓
ComExecutionRunner (serialized through a queue)
    ↓
COM ctrl object (created and executed in the same dedicated thread)
```

Key points:

- gRPC worker threads must not access COM directly.
- COM object creation and execution are fixed to the dedicated `ComExecutionRunner` thread.
- `grpc_server` remains generic; COM-specific constraints are handled in `grpc_com`.
- Because gRPC server handlers execute on a thread pool, directly passing a control object distributes calls across threads and can cause COM corruption or unstable behavior.

Design:

- `ComExecutionRunner` owns a dedicated COM thread and serializes control-object creation and method execution.
- `ThreadSafeCtrlProxy` is the proxy exposed to gRPC and delegates calls to the runner.
- `create_com_grpc_server` is a thin assembly function that combines this mechanism with the existing `create_grpc_server`.

## v0.4.9, nakada

The automatic dispatcher originally attempted to handle properties dynamically as well as methods. This caused failures for control classes containing properties.

Fixed by excluding properties from automatic dispatch.

## v0.4.8, nakada

- Minor fixes.
- Docstring/comment updates.

## v0.4.7, nakada

Dispatch restoration had been one-way:

- list -> tuple

Changed to preserve both types:

- list <-> list
- tuple <-> tuple

## v0.4.6, nakada

- Added pseudo-asynchronous support to the gRPC client.
- Added a gRPC server connection check on the client side.

## v0.4.5, nakada

Bug fixes and additional comments.

## v0.4.4, nakada

- Moved the pyi generation script for dynamically dispatched clients into the framework so it can be used generically.
- Updated `make_pyi.py` for dispatched base/derived classes.

## v0.4.3, nakada

Tested Event mode and made minor modifications based on the results.

- Fixes based on v0.4.2 testing.
  - Verification of standard gRPC functionality as a transparent frame.

## v0.4.2, nakada

Relatively large update.

- Added separate proto definitions for event-related functionality.
- Added a gRPC event-processing mechanism to the client/server framework.
- Modules using the framework can use events when required.

## v0.4.1, nakada

Refactored `build_proto.py` into functions so that it can be used more easily with multiple proto files, with separate Python scripts invoking it for each proto.

Added multi-proto support.

The extended functionality was not yet tested.
Testing and modifications were in progress to ensure operation outside the Joypad use case.

## v0.4.0, nakada

- Extended gRPC Frame with generic event-waiting functionality:
  - Existing normal functionality remains unchanged.
  - Communication occurs only when a high-speed event is generated.
  - The client can wait for events without continuous communication.
  - Other event-driven behavior can be implemented.

- Extended functionality was not yet tested.

## v0.3.4, nakada

Completed Joypad/server operation testing.

- grpc_frame: 0.3.4
- fastapi_frame: 0.4.7
- cobotta2: 0.9.23

## v0.3.3, nakada

Bug fix.

## v0.3.2, nakada

A specific method can suppress frame logging:

```python
# Suppress frame logging only for get_error_count
client.get_error_count._frame_silent = True
```

A related issue is how to reliably override a dynamically dispatched server method on the client side. A mechanism is required so that the client-side override remains stable. The server-side support for this was implemented in this version, based on the approach tested with cobotta-RestAPI.

```python
class JoyPadClient(GrpcClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # ---- Replace the method completely ----
    def drive(self, x: float, y: float, z: float) -> bool:
        """
        drive completely redefined on the user side
        """

        # User-side processing such as logging, preprocessing,
        # and conditional handling
        print("[JoyPadClient] drive override")

        # Explicitly call the original RPC dispatcher
        return self._raw_drive(x, y, z)
```

## v0.3.1, nakada

Removed logs that were rarely useful even during debugging.

## v0.3.0, nakada

Minimum operation tests completed successfully:

- Joypad movement.
- Opening and closing the hand with the Joypad.

Because these operations worked, arbitrary method invocation, including handling of default arguments and optional arguments, was considered broadly functional.

## v0.3.0bata, nakada

### Beta version

- Joypad operation was tested.
- Development originally started with changes required for hand extensions, but those extensions had not yet been implemented, so operation testing remained incomplete.

### Overview

Fixed inadequate handling of method arguments—especially default values—when dynamically exposing a Python-side control object through the client/server framework.

This led to a major redesign of the basic architecture.

- Information that had depended on proto definitions and control classes was moved into the communication layer:
  - Using JSON-form data in the communication layer carries the required invocation information.
  - The client no longer depends on the control class or its proto definition.
  - Proto files that previously had to be rewritten for each control class were consolidated into a generic proto definition.
  - Invocation information is carried as serialized data through a single generic proto interface.

```text
[ Python client ]
    ↓  (*args, **kwargs)
[ client adapter ]
    ↓  (JSON)
[ gRPC / proto ]
    ↓  (JSON)
[ server adapter ]
    ↓  (*args, **kwargs)
[ ctrl (pure Python) ]
```

### proto

Previously, the gRPC proto defined the structure of the transferred data. This was removed, and the protocol now exchanges byte sequences instead.

```text
message CallRequest {
  string method = 1;
  bytes args_json = 2;
  bytes kwargs_json = 3;
}
```

- The proto layer does not know argument names, types, or semantics.
- There is one generic proto definition.
  - Only the caller depends on the method name; invocation information is serialized and supplied by the caller.

### server

gRPC client/server design:

- The Python client accepts fully generic `(*args, **kwargs)`.
  - Editor-visible signatures are provided through pyi files, so the interface appears conventional to the editor.
- Pure-Python interfaces such as `xx(pos, force=force)` are defined in pyi.
- The client does not need to know the control class or control-specific proto/stub definitions.
  - Only the caller depends on the method name; invocation information is serialized by the caller.

On the control side, the server adapter converts the serialized data back into `(*args, **kwargs)`, and the pure-Python control method is then called in a normal form such as `xx(pos, force=force)`.

## v0.2.1, nakada

- Bug fix.

## v0.2.0, nakada

- Refactored an unmaintainable spaghetti-code state into a maintainable structure.
- Split `dispatch_core` functionality according to server/client/core dependencies.
- Added proto and dispatch tests suitable for more complete ORiN-like interface/API rules, including commands such as `drive()`.

## v0.1.2, nakada, **bug**

Renumbered because it was unclear whether the tag had been created previously.

However:

- An unusual/incorrect change was accidentally included and the version became inconsistent.
- **Broken version.**

## v0.1.1, nakada

- Reviewed `dispatch_core`.

## v0.1.0, nakada

Separated from the cobotta2 Joypad implementation.
