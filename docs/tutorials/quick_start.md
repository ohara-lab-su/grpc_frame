# Quick Start

## インストール

- PIXet Pro をインストール
- Python API を利用可能に設定
- mini_pix をインストール

## ローカル制御

```python
from mini_pix.pixet_ctrl import MiniPixCtrl

pix = MiniPixCtrl()
pix.connect()
```

## gRPC クライアント

```python
from mini_pix.server_grpc import SyncPixetGrpcClient

pix = SyncPixetGrpcClient("127.0.0.1", 50051)
```
