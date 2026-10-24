# Advanced behavior and implementation boundaries

[![en](https://img.shields.io/badge/lang-en-red.svg)](https://ohara-lab-su.github.io/grpc_frame/en/tutorials/advanced.html) [![ja](https://img.shields.io/badge/lang-ja-yellow.svg)](https://ohara-lab-su.github.io/grpc_frame/ja/tutorials/advanced.html)

## Events and streams

The framework has two distinct streaming mechanisms. `GrpcClient.subscribe(topic=..., once=False, source="")` uses `Events/Subscribe` and receives `EventBus` payloads. A control object may implement `_set_event_bus(bus)` to receive the server's bus; `ImageStreamGrpcService` illustrates publishing JPEG frames to a topic and the image client decodes frames locally. Separately, `GrpcClient.stream_call(method_name, *args, **kwargs)` calls `Control/StreamCall` against a server configured with `stream_obj=...`. `stream_obj` is distinct from `ctrl_obj`; it is not included in ordinary `Describe` dynamic binding.

The A&D reader sample uses `prepare_event_measurement()` to combine multiple remote calls (`stream_start`, `event_set_config`, `set_trigger_mode`, `event_arm`) and `wait_event()` to consume a single event. Those methods are application-specific conveniences, not `grpc_frame` APIs.

## Synchronous and asynchronous clients

`SyncGrpcClient` is the synchronous interface. `AsyncGrpcClient` wraps dynamically discovered *synchronous* RPC calls using `loop.run_in_executor(None, ...)`; it is **not** a native `grpc.aio` implementation. Application methods that call asynchronous remote methods must `await` them. The A&D reader's async wrapper demonstrates this pattern.

## Data transport and safety

`adapter` attempts JSON serialization first (including tagged tuples and base64 bytes), falling back to Python pickle when JSON is unavailable. Only communicate with trusted peers: unpickling arbitrary data is unsafe. Serialization is not general object identity preservation. The framework exposes public callable methods by name; `Describe` excludes properties, but this is not a method-level authorization system. Restrict network access and do not expose arbitrary device controls to untrusted clients.

## COM-bound controls

The included `grpc_com` module provides `ComExecutionRunner`, `ThreadSafeCtrlProxy`, and `create_com_grpc_server`. COM device creation and method execution must occur on the same dedicated thread, rather than arbitrary gRPC worker threads. Use that module for thread-affine COM controls instead of passing a COM object directly to a generic worker pool.

## Type hints

Dynamic runtime binding does not automatically provide static type information. The repository's `make_pyi` tooling generates client `.pyi` stubs from a client class and the underlying control class. The A&D reader's `make_pyi.py` shows both sync and async generation. Generate stubs; do not maintain them manually.

## Observed implementation limitations

In the provided `grpc_client.py`, the `grpc_options` argument of `SyncGrpcClient` and `AsyncGrpcClient` is accepted but not forwarded to the base constructor. The underlying `GrpcClient` accepts the options. Avoid claiming large-message options work through the derived constructors until this is corrected in the framework. Likewise, method names matching existing client methods can shadow client APIs during dynamic binding; inspect `_method_table` and use deliberate post-initialization rebinding when necessary.

## Discovery is not authorization

`dispatch_core.list_public_methods()` restricts the methods advertised by `Describe`, but the server-side `Control/Call` resolves `getattr(ctrl_obj, request.method)` directly. The supplied implementation does not verify that the requested name belongs to the advertised method table. A leading underscore and property exclusion therefore do **not** enforce access control. Untrusted clients require server-side method authorization and transport security.
