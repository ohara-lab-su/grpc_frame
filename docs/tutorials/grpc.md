# gRPC Interface

mini_pix は grpc_frame を利用してリモート制御を提供します。

- pixet_grpc_server.py
- SyncPixetGrpcClient
- AsyncPixetGrpcClient

ローカル API とほぼ同じメソッドをネットワーク越しに利用できます。

DeviceProxy に登録することで他の装置と同一の制御モデルで扱えます。
