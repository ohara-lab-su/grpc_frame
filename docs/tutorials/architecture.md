# Architecture

```
Application
    │
MiniPixCtrl
    │
grpc_frame
    │
gRPC Server
    │
PIXet Python API
    │
MiniPIX Detector
```

MiniPixCtrl は PIXet Python API の上位制御層です。

gRPC サーバは MiniPixCtrl を公開し、SyncPixetGrpcClient および AsyncPixetGrpcClient から同一 API で利用できます。
