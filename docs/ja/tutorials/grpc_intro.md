# チュートリアル：ローカル制御クラスから透過型プロキシへ

[![en](https://img.shields.io/badge/lang-en-red.svg)](https://ohara-lab-su.github.io/grpc_frame/en/tutorials/grpc_intro.html) [![ja](https://img.shields.io/badge/lang-ja-yellow.svg)](https://ohara-lab-su.github.io/grpc_frame/ja/tutorials/grpc_intro.html)

## 1. 設計思想と呼び出し経路

`grpc_frame` の基本は、**サーバー側に存在するPython制御クラスの公開メソッドをクライアントから透過的に呼び出す**ことです。サーバーの `dispatch_core.list_public_methods()` は `dir()` と `inspect.getattr_static()` を使い、`@property` を評価せず、先頭が `_` のメソッドやプロパティを `Describe` の対象から除外します。クライアントは `Describe` でメソッド名とシグネチャを取得し、`setattr` でRPCディスパッチャを動的に生成します。実行時には `adapter` が引数を変換し、`Call` RPCを介してサーバーの元の制御オブジェクトのメソッドを呼び出します。

```text
クライアント → 動的メソッド → adapter → gRPC Call
  → サーバーディスパッチ → 元の制御クラス → 戻り値 → クライアント
```

透過的なのは**メソッド呼び出し**です。オブジェクトのメモリやファイルシステムを共有するわけではありません。現在の実装は `grpc.insecure_channel` を使うため、信頼できるネットワーク内で運用するか、通信保護を別途設計してください。

## 2. 最小構成

```text
example/
  simple_ctrl.py
  server_grpc/
    __init__.py
    server.py
    client.py
  client.py
```

`simple_ctrl.py` は通信機能を持たない制御クラス、`server_grpc/server.py` はサーバーの起動、`server_grpc/client.py` はアプリケーション用のクライアントクラス、`client.py` は使用例です。実行可能なソース一式はリポジトリの `example/` に収録しています。接続先は各ファイル先頭の `HOST`、`PORT` を変更します。

## 3. 制御クラスとサーバー

`SimpleCtrl` は `set_value()`、`get_value()`、`status()`、`save_on_server()` を提供します。実機制御クラスも同様に、gRPCを意識せずローカルの機器制御ロジックを実装します。サーバーは `create_grpc_server(ctrl_obj=SimpleCtrl())` で生成し、`add_insecure_port()`、`start()`、`wait_for_termination()` で起動・維持します。旧チュートリアルにあった内部クラス `_ControlServicer` の直接利用や、サーバー起動後のサービス登録は不要です。

## 4. クライアントと自動ディスパッチ

`SimpleClient(SyncGrpcClient)` の `super().__init__()` はサーバーへ接続して `Describe` を実行し、公開メソッドをクライアントのインスタンスにバインドします。`client.set_value(12.5)`、`client.get_value()`、`client.status()` は通常のPythonメソッドのように記述できますが、処理本体はサーバーで実行されます。単純なRPCだけならクライアント専用サブクラスは必須ではありません。ただし、クライアント固有の処理、引数の変換、利便メソッド、上書き処理はサブクラスにまとめるのが適切です。

## 5. ファイル保存の実行場所

RPCで `save_on_server("data.txt")` を呼ぶと、**サーバー側**のファイルシステムに保存されます。クライアント側に保存したい場合は、`get_value()` などでデータを取得し、クライアント側の `Path.write_text()` 等で保存します。例題の `SimpleClient.save_on_client()` がその処理です。

ここで注意が必要です。現行の `_bind_remote_methods()` は `setattr(self, name, dispatcher)` により**インスタンス属性**を作るため、同名のサブクラスメソッドを普通に定義しただけでは上書きされます。そこで `SimpleClient.__init__()` は `super().__init__()` **の後で** `self.save_on_server = self._save_on_client_override` を設定し直しています。元のRPC呼び出しは `self._raw_save_on_server()` に残っています。これは現在の実装に基づく重要な仕様です。

## 6. 実行方法

`example/` を作業ディレクトリとして、サーバーを `python -m server_grpc.server` で起動し、別の端末から `python client.py` を実行します。`12.5` と状態辞書が表示され、`client_value.txt` と `also_client_value.txt` はクライアント、`server_value.txt` はサーバーに保存されます。同一ホストではファイルシステムが共通なので、保存先の違いを確認するときは別ホストまたは別作業ディレクトリを使用してください。終了時は `client.close()` で通信リソースを解放します。
