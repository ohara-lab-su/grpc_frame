# gRPC Frame

[![en](https://img.shields.io/badge/lang-en-red.svg)](https://ohara-lab-su.github.io/grpc_frame/en/index.html) [![ja](https://img.shields.io/badge/lang-ja-yellow.svg)](https://ohara-lab-su.github.io/grpc_frame/ja/index.html)

[GitHub](https://github.com/ohara-lab-su/grpc_frame/) / [ohara-lab-su documentation](https://ohara-lab-su.github.io/)

```{toctree}
:maxdepth: 2
:caption: Contents:

tutorials/grpc_intro
api/modules
```

gRPC Frame is a communication framework built on gRPC. Its central design principle is a **transparent proxy**: the client can interact with a server-side Python control class using an interface that closely resembles the original class.

It is similar in purpose to [ese774_frame](https://github.com/ohara-lab-su/ese774_frame/), but differs in its API design. While `ese774_frame` uses Pydantic/OpenAPI-oriented interfaces, `grpc_frame` exposes the control class transparently without requiring an explicit interface definition.

The basic communication model is:

```
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

The client can therefore use the remote control class without needing to manage the underlying gRPC communication directly.

`grpc_frame` also supports event-based interaction, allowing events on the server to trigger actions on the client with minimal communication overhead.

---
## Author
- Kengo NAKADA
