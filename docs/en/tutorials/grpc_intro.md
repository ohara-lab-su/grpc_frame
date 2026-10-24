# Tutorial: from local control to remote proxy

[![en](https://img.shields.io/badge/lang-en-red.svg)](https://ohara-lab-su.github.io/grpc_frame/en/tutorials/grpc_intro.html) [![ja](https://img.shields.io/badge/lang-ja-yellow.svg)](https://ohara-lab-su.github.io/grpc_frame/ja/tutorials/grpc_intro.html)

## 1. Design and execution path

`grpc_frame` exposes the public callable methods of a **server-side Python control object**, not its entire object state. The server's `dispatch_core.list_public_methods()` uses `dir()` and `inspect.getattr_static()` to avoid evaluating properties; methods beginning with `_` and `@property` values are not included in `Describe`. The client obtains names and signatures with `Describe` and installs callable dispatchers dynamically with `setattr`. Calls serialize positional/keyword arguments using `adapter`, invoke `/ctrl.Control/Call`, and deserialize the returned value. The server resolves the method on the original control object and executes it there.

```text
client code → dynamically bound method → adapter → gRPC Call
  → server dispatcher → original control object → result → client
```

This is *method-call transparency*, not a shared-memory object, a transparent filesystem, or a security boundary. The transport currently uses `grpc.insecure_channel`; deploy only on trusted networks or add appropriate transport protection.

## 2. Minimal project layout

```text
example/
  simple_ctrl.py             # hardware/control logic; no grpc_frame import
  server_grpc/
    __init__.py
    server.py                # create_grpc_server(ctrl_obj=...)
    client.py                # application-facing SyncGrpcClient subclass
  client.py                  # calling application
```

The complete runnable files are supplied in the repository's `example/` directory. Install the package and run the server first, then the client. Both programs use `HOST = "127.0.0.1"` and `PORT = 50051` in their source; change those values for remote hosts.

## 3. Local control class

`simple_ctrl.py` defines `SimpleCtrl.set_value()`, `get_value()`, `status()` and `save_on_server()`. The class has no knowledge of gRPC. A real instrument driver follows the same pattern: its public callable methods are discoverable, while internal state remains on the server.

## 4. Server

`server_grpc/server.py` constructs the control object and passes it to `create_grpc_server(ctrl_obj=SimpleCtrl())`. The returned gRPC server is bound with `add_insecure_port()`, started, and kept running using `wait_for_termination()`. Unlike the older draft tutorial, do not manually instantiate the private `_ControlServicer` or register it after `server.start()`.

## 5. Client and automatic dispatch

`server_grpc/client.py` defines `SimpleClient(SyncGrpcClient)`. Its constructor calls `super().__init__()`, which connects, requests `Describe`, and binds each discovered remote method. The application can then call `client.set_value(12.5)`, `client.get_value()`, or `client.status()` as if invoking methods on the local control class. The method bodies actually execute on the server.

A dedicated client subclass is optional for plain RPC, but is the appropriate place for client-only operations, argument adaptation, convenience APIs, and explicit overrides.

## 6. Where does a file get written?

A remotely dispatched `save_on_server("data.txt")` executes `SimpleCtrl.save_on_server` on the **server filesystem**. To save on the client instead, call a remote getter and write the result locally, as in `SimpleClient.save_on_client()`.

The example also demonstrates overriding a *remote method name*. `_bind_remote_methods()` creates an **instance attribute** using `setattr(self, name, dispatcher)`. A normal subclass method of the same name would therefore be shadowed. `SimpleClient.__init__()` deliberately reassigns `self.save_on_server = self._save_on_client_override` **after** `super().__init__()`. The original RPC dispatcher is still accessible as `self._raw_save_on_server(...)`. This detail is essential when implementing client-side behavior with the current framework implementation.

## 7. Run and verify

From the `example/` directory, run `python -m server_grpc.server`, then in another terminal `python client.py`. The output should include the value `12.5`, a status dictionary, and three paths. The client saves `client_value.txt` and `also_client_value.txt`; the original remote method saves `server_value.txt` on the server. Always call `client.close()` when finished.
