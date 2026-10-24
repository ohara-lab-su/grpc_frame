# 応用：イベント・ストリーム・非同期・制約

[![en](https://img.shields.io/badge/lang-en-red.svg)](https://ohara-lab-su.github.io/grpc_frame/en/tutorials/advanced.html) [![ja](https://img.shields.io/badge/lang-ja-yellow.svg)](https://ohara-lab-su.github.io/grpc_frame/ja/tutorials/advanced.html)

## イベントとストリーミング

ストリームには別々の2系統があります。`GrpcClient.subscribe(topic=..., once=False, source="")` は `Events/Subscribe` により `EventBus` のイベントを受信します。サーバー側の制御クラスは `_set_event_bus(bus)` を実装すればバスを受け取れます。`image_server` の `ImageStreamGrpcService` はJPEG画像をトピックへ配信し、クライアント側で復号する例です。一方、`GrpcClient.stream_call(method_name, *args, **kwargs)` は、`stream_obj=...` を設定したサーバーの `Control/StreamCall` を使います。`stream_obj` は通常の `ctrl_obj` と異なり、`Describe` による動的バインドの対象ではありません。

A&D readerの例では、`prepare_event_measurement()` が `stream_start`、`event_set_config`、`set_trigger_mode`、`event_arm` という複数のリモート操作をまとめ、`wait_event()` でイベントを待ちます。これらはA&D reader固有の便利メソッドであり、`grpc_frame` 本体のAPIではありません。

## 同期・非同期クライアント

`SyncGrpcClient` は同期呼び出し用です。`AsyncGrpcClient` は同期gRPC呼び出しを `loop.run_in_executor(None, ...)` で実行する方式であり、**ネイティブの `grpc.aio` 実装ではありません**。非同期クライアントで動的バインドされたメソッドは `await` が必要です。A&D readerの非同期クライアントがその使用例です。

## データ形式とセキュリティ

`adapter` はJSONによるシリアライズを優先し、タプルとbytesを専用表現で処理します。JSON化できない場合はpickleへフォールバックします。pickleの復元は任意コード実行につながるため、**信頼できる相手とだけ通信してください**。一般のPythonオブジェクトを完全に同一の状態で共有する機構ではありません。また、公開メソッドの列挙は認可機能ではないため、外部公開する場合はネットワークアクセスを制限してください。

## COM制御

`grpc_com` の `ComExecutionRunner`、`ThreadSafeCtrlProxy`、`create_com_grpc_server` は、COMの生成とメソッド実行を専用スレッドへ固定する仕組みです。gRPCワーカースレッドからCOMオブジェクトを直接操作せず、この補助モジュールを利用します。

## 型補完

動的ディスパッチだけではIDEに制御クラスの型情報が伝わりません。`make_pyi` の生成機能を利用して、元の制御クラスとクライアントクラスから `.pyi` を自動生成します。A&D readerの `make_pyi.py` は同期・非同期両方の生成例です。`.pyi` を手書きする必要はありません。

## 実装上の注意

提供された `grpc_client.py` では、`SyncGrpcClient` と `AsyncGrpcClient` のコンストラクタが `grpc_options` を受け取りますが、基底クラスに転送していません。大容量データ用の設定が派生クラス経由で反映されるとは断定できません。また、動的バインドされた名前が既存のクライアントメソッドと衝突すると、インスタンス属性が優先されます。必要に応じて `_method_table` を確認し、初期化後に明示的に再バインドしてください。

## Describe と RPC 呼び出し許可の違い

`dispatch_core.list_public_methods()` は `Describe` の表示対象を絞りますが、サーバー側の `Control/Call` は `getattr(ctrl_obj, request.method)` で直接メソッドを解決します。現行コードでは `Describe` に含まれない名前を拒否する検査がありません。`_` 接頭辞やプロパティ除外はアクセス制御ではなく、信頼できないクライアントからの呼び出しを防ぎません。サーバーを外部公開する場合はサーバー側の許可リストと認証などが別途必要です。
