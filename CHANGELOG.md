# README

## v0.5.14, 2026-10-05, K.Nakada

- README 修正
 
## v0.5.13, 2026-10-05, K.Nakada

- toml 修正
- PyPI 対応

## v0.5.12, 2026-10-05, K.Nakada

grpc_frame 内の proto build / maintenance utility を整理

- proto 生成・清掃用スクリプトを `grpc_frame/util/` に移動
  - `build_proto.py`
  - `build_proto_ctrl.py`
  - `build_proto_events.py`
  - `clean_proto.py`
  - `clean_site_packages.py`

- utility の配置変更に伴い、proto ファイルおよび生成ファイルのパス処理を修正
  - `ctrl.proto` / `events.proto` は従来どおり `grpc_frame/` 直下に配置
  - 生成される `ctrl_pb2.py` / `ctrl_pb2_grpc.py` / `events_pb2.py` / `events_pb2_grpc.py` も従来どおり `grpc_frame/` 直下に生成
  - build utility 自体の配置場所と、proto の入力・生成先を分離

- 個別 proto build スクリプトの import 処理を修正
  - `build_proto_ctrl.py` / `build_proto_events.py` から `grpc_frame` package を経由せず、同一 `util/` 内の `build_proto.py` を直接利用
  - pb2 ファイルが未生成の状態でも個別 build を実行できるようにした

### ディレクトリ構成

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

proto および生成された pb2 は grpc_frame 本体から直接利用するため従来の配置を維持し、build・clean など開発／保守用のスクリプトのみ `util` に分離した。

## v0.5.11, 2026-08-10, K.Nakada

汎用ディスパッチに server-streaming RPC を追加

- `ctrl.proto` の `Control` service に `StreamCall` を追加
  - `rpc StreamCall(DispatchRequest) returns (stream DispatchResponse);`
  - 既存の `Call` は通常の unary RPC としてそのまま維持
  - `DispatchRequest` / `DispatchResponse` も既存定義をそのまま利用

- `grpc_server.py` / `grpc_client.py` に `StreamCall` の処理を追加
  - `Call`：1回の呼び出しに対して1つの結果を返す通常の汎用ディスパッチ
  - `StreamCall`：1回の呼び出しに対して複数の結果を順次返す汎用 server-streaming ディスパッチ
  - streaming するデータの種類や用途は grpc_frame 側では規定しない

### 設計

従来の grpc_frame は、`Call` によってデバイス側の Python メソッドを透過的に呼び出す
汎用 unary RPC を基本としている。

今回、この基本設計は変更せず、gRPC が標準で持つ server-streaming RPC を
同じ汎用ディスパッチの考え方で扱えるよう `StreamCall` を追加した。

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

- after cobotta3/4 setup
 
# v0.5.9, 2026.07.14, nakada 

- 八代研引き渡し版
 
## v0.5.8, (2026.07.09), K.Nakada

gRPC の大容量メッセージ option 指定に対応

- gRPC channel/server 作成時に任意の `grpc_options` を渡せるようにした
  - `grpc_frame.grpc_client.GrpcClient` に `grpc_options` 引数を追加
  - `grpc_frame.grpc_server.create_grpc_server()` に `grpc_options` 引数を追加
  - `grpc_frame.grpc_com.create_com_grpc_server()` に `grpc_options` 引数を追加
- `grpc_options` は `grpc.insecure_channel()` および `grpc.server()` にそのまま渡す
- 大きな `bytes` 戻り値を unary RPC で扱う用途に対応
  - 例: BMP 画像のように gRPC Python の既定上限 4 MB を超えるデータ
  - 利用側で `grpc.max_receive_message_length` / `grpc.max_send_message_length` を指定可能にした
- 既定値は従来互換とし、`grpc_options` 未指定時は空 tuple を使う
- COM 対応 server でも通常 server と同じ option 指定ができるようにした
  - `create_com_grpc_server()` から `create_grpc_server()` へ `grpc_options` を透過する


## v0.5.7, (2026.06.29), K.Nakada

DeviceProxy 対応を追加

- ese774_frame の DeviceProxy と互換の entry API を grpc_frame 側に追加
  - DeviceProxyEntry
  - register_device_proxy()
  - unregister_device_proxy()
  - get_device_proxy_entry()
  - list_device_proxies()
  - DeviceProxy()
  - create_device_proxy()
- 直接の client_class を登録し、device_class 名または alias から client インスタンスを生成できるようにした
- sync/async client class の登録に対応
- default_async_mode により DeviceProxy() の既定生成モードを指定可能にした
- DeviceProxy 用 pyi 生成補助を追加
- grpc_frame.__init__ から DeviceProxy 関連 API を公開

## v0.5.6, (2026.04.30), K.Nakada

pyproject.toml 再調整
- 3.7
- 3.11.9
- 3.13.13

## v0.5.5, (2026.04.30), K.Nakada

- setuptools 82 環境での grpc_tools の不具合を修正
  - build_proto.py

## v0.5.4, K.nakada

python 3.7 対応(まだ未完の可能性)

## v0.5.3, K.nakada

- min_pix 検出器対応のために python 3.7 対応
- そのために gRPC を落とす。toml 書き換えた他のバージョンと切り替え

## v0.5.2, K nakada

- 出張前 FINALバージョン(2026.03.15)
- ドキュメント調整

## v0.5.1, K nakada

ドキュメント調整

## v0.5.0, (v0.4.10+fix),k nakada

COM スレッド問題対応版 (ORIN2-gRPC/FastAPI対応版)

0.4.10思ったより改変が大きいので別バージョン名
- bugfix: gRPC で cobotta2 の本番を使った時のトラブル対応
  - 修正: _collect_public_method_names
  - 修正: _collect_signatures
 
## v0.4.10, nakada

例外処理が出た時がうまくクライアント側に伝わってない問題が発覚
- 問題解決のためにも、基本的に例外が起きた時には、例外の生メッセージをまず送る
- スレッド問題
  - COM のインスタンスから呼びだれる各種メソッドを
  - gRPCでハンドラ単位でスレッドにしてしまっているのが
  - 実は大きな問題で、これが例外の主な原因になる。

### COM スレッド問題

windows の COM を同一のメモリである必要がある。
つまり別スレッドだとだめ。COMの初期化をし直さないといけない。

そのため gRPC などでは別スレッドでハンドラが動くしくみなのだが、
通常は、スレッドなのでメモリはシェアなので考えなくてもいいのだが。

COM だと、別スレッドで動いてしまうと、その状況を破壊する。
その対策で制御側のコンストラクタで一回だけの初期化ではなくて
gRPCハンドラースレッドでCOMを初期化するようにする。
ハンドラースレッド（COM初期化パート）を、いろいろなハンドラー呼び出しで
使いまわせる用意、quque で命令をためて切り分ける

つまり、grpc.serverを使うと、RPC ハンドラ
（_ControlServicer.Describe/Call） は
ThreadPoolExecutor のワーカースレッドで実行される。
一方で、orin2_grpc_server.py の ctrl = ... という
「制御インスタンス生成」はメインスレッド（server を起動しているスレッド）
で行われます。したがって「通常版（素の ctrl を _ControlServicer に渡す）」
は、メインスレッドで作った COM オブジェクトを、別スレッド（ハンドラ）か
ら触る構図になり、COM では破綻する

- 通常はgRPC はワーカースレッドとメインスレッド(server起動スレッド)の二つとなるのがミソ

gRPC Client
- grpc_server._ControlServicer (gRPC worker thread)
- ThreadSafeCtrlProxy
- ComExecutionRunner (queueで直列化)
- COM ctrl object (同一スレッドで生成/実行)

要点
- gRPC worker thread から COM を直接触らない
- COM の生成/実行は ComExecutionRunner の専用スレッドに固定
- grpc_server は汎用のまま、COM制約は grpc_com 側で吸収する
- gRPC サーバーは ThreadPool 上で handler が動くため、ctrl を直接渡すと
  呼び出しスレッドが分散し、COM 破壊や不安定動作の原因になる。

設計
- ComExecutionRunner が COM 専用スレッドを持ち、ctrl 生成とメソッド実行を一本化する。
- ThreadSafeCtrlProxy は gRPC 側に見せる代理で、呼び出しを runner に委譲する。
- create_com_grpc_server は既存 create_grpc_server と組み合わせるための薄い組み立て関数。

## v0.4.9, nakada

自動ディスパッチで何も考えずに propery まで動的に自動で対応しているので、
プロパティがあるctlの時に失敗する問題に気がつく

修正(properyを除外する)

## v0.4.8, nakada

- 細かい修正
- docstring/comment

## v0.4.7, nakada

dispatch 復元が一方通行だったので
- list -> tuple

これを
- list <-> list
- tuple <-> tuple

に修正

## v0.4.6, nakada

- gRPC client の擬似Async化 追加
- gRPC client 側に gRPC srver との接続チェック

## v0.4.5, nakada

bugfix/コメント追加

## v0.4.4, nakada

- ディパッチされる client 用の pyi 作成スクリプトを
汎用的に使えるように、フレーム側に入れる
- make_pyi.py 修正(dispatchされる継承元と継承先)

## v0.4.3, nakada

Event モードの動作テストおよびそれに対して若干の改修

- v0.4.2 の動作確認による修正
  - grpc 標準機能の確認(透過型frameとして)

## v0.4.2, nakada

割と大改修

- event 関係の proto 周りを別途追加
- gRPC での event 処理の仕組みを(client/serverフレーム側に導入)
- 必要ならば、module 利用先で event を用いることができる

## v0.4.1, nakada

build_proto.py を
複数 proto で使いやすくするタメに
関数化して、proto毎にそれを呼び出す
python にする

複数 proto 対応

拡張機能は未テスト。
gRPCフレームで joypad 外の動作保証のためのテストと改修中

## v0.4.0, nakada

- gRPC Frame 拡張 (汎用的なevent待受機能)
  - ノーマルの機能はそのまま
  - 高速でイベントが発生した時だけの通信発生
  - クライアントでのイベント待機（通信は発生しない)
  - などが実現できる
 
- 拡張機能は未テスト。

## v0.3.4, nakada

jopad/server 動作テスト対応完了
 
- grpc_frame: 0.3.4
- fastapi_frame: 0.4.7
- cobotta2: 0.9.23

## v0.3.3, nakada

bugfix

## v0.3.2, nakada

```python
# get_error_count だけ frame logging を抑止
client.get_error_count._frame_silent = True
```
として、特定のメソッドだけログを表示しないようにすることができる

また、似ている話で、 サーバー側で動的にディスパッチされるメソッドを
クライアント側で安定的にオーバーライドさせるために、
工夫が必要となる。(サーバー側の仕掛けを今回実装/cobotta-RestAPIで試した方法)

```python
class JoyPadClient(GrpcClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # ---- メソッド丸ごと置き換え ----
    def drive(self, x: float, y: float, z: float) -> bool:
        """
        ユーザ側で完全に再定義された drive
        """

        # ユーザ側処理（ログ・前処理・条件分岐など）
        print("[JoyPadClient] drive override")

        # 元の RPC dispatcher を明示的に呼ぶ
        return self._raw_drive(x, y, z)
```


## v0.3.1, nakada

デバッグでもあまり使わないログを消去

## v0.3.0, nakada

- 最低限のテスト
- Joypad 移動
- Joypad での Hand 開け閉め

が動作したので、任意の Method 動作は(デフォルト値・有無)
概ね機能している

## v0.3.0bata, nakada

### beta版
 
- Jopad での操作はテスト済み
- ハンドの拡張に伴う修正が始まりだったのだがそれはまだ未実装なのでまだ動作テスト不全

### 内容の概要 

python側の ctrl を動的に clinet/server にするときに、
method の引数処理の特にデフォルト値の扱いがいい加減だったものを修正

これが大修正につながる。
基本方針を大きく変える

- proto や ctrl に依存していた情報を
  - 通信レイヤーを json 型にすることで情報を載せることで解決
  - クライアント側で proto/ctrl 依存を消すことができる
  - ctrl ごとに書き直していた proto を無修正の汎用 proto にまとめる
    - 情報をjsonでまとめるだけの一つの proto

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

### proto

今までは gRPC proto に構造を(転送するdataに構造を)
定義して持たせていたが。これを完全に無くして
byte 列をやりとりする

```aiignore
message CallRequest {
  string method = 1;
  bytes args_json = 2;
  bytes kwargs_json = 3;
}
```

- proto 側は、引数名も型もいみもしらない。
- proto 側の定義は一つ
  - (メソッド名は呼び出し側のみ依存して、呼び出し情報は常に呼び出し側が情報を json でのせる)

### server

gRPCクライアント/サーバ

- python clinet は完全な一般の (*args, **kwargs)
  - pyi から補完できるようにするので editor からみれば従来通り見える
- pure python xx(pos, force=force)などの形は pyi で定義する
- client 側は ctl も proto (スタブも) しらない
  - メソッド名は呼び出し側のみ依存して、呼び出し情報は常に呼び出し側が情報を json でのせる

ctrl側では一旦、server adapter 側で jON を (*args, **kwargs)にして、
ctrl 側の pure python で xx(pos, force=force)などにする。


## v0.2.1, nakada

- bugfix

## v0.2.0, nakada

- 保守でないスパゲティ状態だったので、保守可能レベルに直した
- dispatch_core 機能をserver/client/core 側に依存があるものは分けた
- drive()命令など、本格的にorinっぽいI/F APIルールに使える proto とディスパッチテスト

## v0.1.2, nakada, **bug**

タグを打ち忘れたかどうかを忘れたのでもう一度ナンバリング

しかし... 
 
- 非常に変ものが入ってしまってごちゃごちゃになったやつ
- **腐っている**

## v0.1.1, nakada

- dispatch core 見直し
 

## v0.1.0, nakada

cobotta2 joypad から分離
