# gRPC Frame

[![en](https://img.shields.io/badge/lang-en-red.svg)](https://github.com/ohara-lab-su/grpc_frame/blob/main/README.md)
[![ja](https://img.shields.io/badge/lang-ja-yellow.svg)](https://github.com/ohara-lab-su/grpc_frame/blob/main/README.ja.md)

gRPC Frame は、Python の制御クラスを gRPC
経由で遠隔利用するための通信フレームワークです。

基本コンセプトは **透過型プロキシ**
です。サーバー側に配置した制御クラス（`ctrl` object）の public method
を自動的に列挙し、クライアント側へ同名の Python method
として動的に生成します。そのため、通常の unary RPC
を追加するたびに個別の protobuf message や RPC method
を定義し直す必要はありません。

機器制御、実験装置、計測サーバー、ラボオートメーションなど、「既存の
Python
制御クラスをネットワーク越しにほぼ同じ呼び出し方で利用したい」用途を想定しています。

> gRPC Frame が公開するのは、制御オブジェクトの **public callable**
> です。`property`
> は列挙時の副作用を避けるため公開対象から除外されます。

------------------------------------------------------------------------

## 特徴

-   サーバー側の public method を `Describe` RPC で自動取得
-   クライアント側へ remote method を動的バインド
-   `*args` / `**kwargs` をそのまま汎用 RPC へ渡せる構成
-   通常の unary call に加えて server-streaming の `StreamCall` を提供
-   topic ベースの event subscribe に対応
-   JSON を優先し、JSON 化できない Python object は pickle
    へフォールバック
-   `bytes` / `bytearray`、`tuple` を JSON 経由でも保持
-   同期クライアントと async wrapper を提供
-   DeviceProxy registry により機器クラス名から client を生成可能
-   protobuf の generated Stub に依存せず、gRPC low-level API から RPC
    を構築

------------------------------------------------------------------------

## 基本構成

通常のメソッド呼び出しは、概念的には次の経路を通ります。

``` text
[ Python client ]
        |
        |  method(*args, **kwargs)
        v
[ GrpcClient dynamic dispatcher ]
        |
        |  adapter.pack_args / pack_kwargs
        v
[ DispatchRequest ]
        |
        |  gRPC
        v
[ Control service ]
        |
        |  unpack args / kwargs
        v
[ ctrl object (pure Python) ]
        |
        |  return value
        v
[ DispatchResponse ]
        |
        |  adapter.unpack_result
        v
[ Python client ]
```

クライアントは接続時に `Control/Describe`
を呼び出します。サーバーから返された method name と signature
を基に、`self.<method_name>` が動的に生成されます。

たとえばサーバー側の制御クラスに

``` python
class SimpleCtrl:
    def ping(self) -> str:
        return "pong"

    def add(self, a: int, b: int) -> int:
        return a + b
```

が公開されていれば、クライアント側では概念的に

``` python
client.ping()
client.add(10, 20)
```

のように呼び出せます。

`ping` や `add` ごとの専用 RPC を protobuf に追加するのではなく、共通の
`Call` RPC が method name、args、kwargs を受け取り、サーバー側で対象
method を dispatch する設計です。

------------------------------------------------------------------------

## RPC インターフェース

### Control service

`ctrl.proto` では次の 3 種類の RPC を定義します。

``` proto
service Control {
  rpc Describe(Empty) returns (MethodTable);
  rpc Call(DispatchRequest) returns (DispatchResponse);
  rpc StreamCall(DispatchRequest) returns (stream DispatchResponse);
}
```

### `Describe`

サーバー側の公開可能な method 一覧を取得します。

各 method について以下を返します。

-   method name
-   `inspect.signature()` から得た signature 文字列

公開対象は public callable です。名前が `_` から始まる member
は除外されます。また、`property` は値の取得によって COM
呼び出しや機器アクセスなどの副作用が起きる可能性があるため、静的に判定して除外します。

### `Call`

通常の 1 request / 1 response の汎用 method call です。

``` proto
message DispatchRequest {
  string method = 1;
  bytes args = 2;
  bytes kwargs = 3;
}

message DispatchResponse {
  bool ok = 1;
  bytes result = 2;
  string error = 3;
}
```

クライアントは Python の positional arguments と keyword arguments を
`bytes` へ変換し、method name とともに送信します。正常終了時には result
を Python object へ復元します。サーバー側が error
を返した場合、クライアントは `RuntimeError` を送出します。

### `StreamCall`

1 回の request に対して複数の response を返す server-streaming RPC
です。

クライアントでは明示的に

``` python
for value in client.stream_call("method_name", arg1, arg2):
    print(value)
```

のように利用します。

通常の `Describe` → dynamic binding → `Call` とは独立した低レベル API
です。

------------------------------------------------------------------------

## イベント通信

gRPC Frame は通常の method call だけでなく、server-side streaming
を使った event subscribe を持ちます。

`events.proto` の定義は次の通りです。

``` proto
service Events {
  rpc Subscribe(SubscribeRequest) returns (stream Event);
}
```

購読要求には以下を指定できます。

-   `topic`: 購読する topic
-   `once`: 1 event だけ受信して終了するか
-   `source`: event source の識別情報

クライアント側では、

``` python
for payload in client.subscribe(topic="status"):
    print(payload)
```

または 1 件だけ取得する場合、

``` python
for payload in client.subscribe(topic="status", once=True):
    print(payload)
```

のように扱います。

内部の `EventBus` は in-process の軽量 publish/subscribe 機構です。topic
ごとに subscriber queue を持ち、`threading.Condition` を使って publish
と subscribe を同期します。

現行の `EventBus` 実装では `source`
は購読状態として保持されていますが、publish 時の source filtering
にはまだ使用されていません。この点は将来拡張用のフィールドです。

------------------------------------------------------------------------

## シリアライズ

引数、戻り値、event payload の変換は `adapter` が担当します。

基本方針は **JSON first + pickle fallback** です。

1.  まず JSON serialization を試す
2.  JSON 化できない object は pickle へフォールバックする

payload の先頭 1 byte には形式識別子が付加されます。

  識別子   形式
  -------- --------
  `b"J"`   JSON
  `b"P"`   pickle

### JSON での追加対応

標準 JSON では直接扱えない一部の型も adapter 側で保持します。

-   `bytes` / `bytearray`: Base64 に変換
-   `tuple`: 専用 marker を付けて list と区別し、decode 時に tuple
    へ復元

これにより、一般的な dict / list / str / int / float / bool / `None`
に加え、binary data や tuple も JSON 経路で扱えます。

### pickle fallback に関する注意

pickle は Python object を広く扱える一方、信頼できないデータの
deserialize には適しません。gRPC Frame
を信頼できないネットワークへ直接公開する場合は、pickle を含む現在の
serialization model と non-TLS channel
の双方を考慮し、ネットワーク分離、認証、TLS、serialization policy
の制限などを別途設計してください。

------------------------------------------------------------------------

## クライアント

### `GrpcClient`

基本クライアントです。

``` python
from grpc_frame.grpc_client import GrpcClient

client = GrpcClient(
    server_ip="127.0.0.1",
    server_port=50051,
    timeout_sec=5.0,
)

print(client.is_connected())

result = client.add(10, 20)
print(result)

client.close()
```

初期化時には次の処理が行われます。

1.  `grpc.insecure_channel()` で channel を作成
2.  gRPC server が ready になるまで確認
3.  `Describe` RPC を実行
4.  method table を取得
5.  各 remote method の dispatcher を生成
6.  `self.<method_name>` と `_raw_<method_name>` へ登録

`is_connected()` は `Describe` RPC
が実際に成功するかどうかで接続状態を確認します。

### gRPC options

`GrpcClient` は `grpc_options` を受け取れます。大きな画像や binary data
を転送する場合には、たとえば gRPC message size に関する option
を指定できます。

``` python
options = (
    ("grpc.max_receive_message_length", 32 * 1024 * 1024),
    ("grpc.max_send_message_length", 32 * 1024 * 1024),
)

client = GrpcClient(
    server_ip="127.0.0.1",
    server_port=50051,
    grpc_options=options,
)
```

サーバー側にも対応する設定が必要です。

### `SyncGrpcClient`

同期 API 用の client class です。remote method
は通常の関数呼び出しとして利用します。

``` python
from grpc_frame.grpc_client import SyncGrpcClient

client = SyncGrpcClient(
    server_ip="127.0.0.1",
    server_port=50051,
)

value = client.ping()
```

### `AsyncGrpcClient`

`Describe` で取得した remote method を async method でラップします。

``` python
import asyncio
from grpc_frame.grpc_client import AsyncGrpcClient


async def main() -> None:
    client = AsyncGrpcClient(
        server_ip="127.0.0.1",
        server_port=50051,
    )

    value = await client.ping()
    print(value)
    client.close()


asyncio.run(main())
```

現行実装では `grpc.aio` による native async RPC ではなく、同期 remote
method を event loop の executor で実行する wrapper です。

------------------------------------------------------------------------

## DeviceProxy

`device_proxy.py` は、機器クラス名と client class の対応を registry
へ登録し、名前から client instance を生成する仕組みを提供します。

主な API は以下です。

``` text
DeviceProxyEntry
register_device_proxy(...)
unregister_device_proxy(...)
get_device_proxy_entry(...)
list_device_proxies()
DeviceProxy(...)
create_device_proxy(...)
```

登録例:

``` python
from grpc_frame.device_proxy import register_device_proxy

register_device_proxy(
    "MyDeviceCtrl",
    sync_client_cls=MySyncClient,
    async_client_cls=MyAsyncClient,
    aliases=["my_device"],
)
```

生成例:

``` python
from grpc_frame.device_proxy import DeviceProxy

client = DeviceProxy(
    "MyDeviceCtrl",
    "127.0.0.1",
    50051,
    async_mode=False,
)
```

直接 client class が登録されていない場合は、汎用の `SyncGrpcClient` /
`AsyncGrpcClient` へフォールバックできます。

`api_spec` と `object_name` は互換性および tooling 用 metadata
として保持されます。runtime の method discovery 自体は `Describe` RPC
によって行われます。

------------------------------------------------------------------------

## 制御クラスの設計

gRPC Frame へ渡す制御クラスは、通常の Python class として記述できます。

``` python
from typing import Any, Dict, List, Optional, Tuple


class SimpleCtrl:
    def __init__(self, name: str = "simple") -> None:
        self._name = name
        self._counter = 0

    @property
    def name(self) -> str:
        return self._name

    def ping(self) -> str:
        return "pong"

    def add(self, a: int, b: int) -> int:
        return a + b

    def echo(self, msg: str) -> str:
        return msg

    def sum_list(self, values: List[float]) -> float:
        return float(sum(values))

    def mix(
        self,
        a: int,
        b: int = 1,
        *,
        scale: float = 1.0,
        tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        value = (a + b) * scale
        return {"value": value, "tag": tag}

    def make_tuple(self, a: int, b: str) -> Tuple[int, str]:
        return (a, b)

    def get_state(self) -> Dict[str, Any]:
        self._counter += 1
        return {
            "name": self._name,
            "counter": self._counter,
        }
```

この場合、`ping`、`add`、`echo`、`sum_list`、`mix`、`make_tuple`、`get_state`
は public callable として discovery の対象になります。

一方、`name` は `property` なので `Describe` の公開 method
には含まれません。

------------------------------------------------------------------------

## protobuf をどこまで書く必要があるか

通常の制御 method を追加するだけであれば、method ごとに protobuf RPC
を追加する必要はありません。

たとえば `SimpleCtrl` に

``` python
def reset(self) -> None:
    ...
```

を追加し、サーバー側の `ctrl_obj` として公開すれば、`Describe` が
`reset` を検出し、接続時にクライアントへ `reset()`
が動的に追加されます。

つまり、通常の制御 API については、

``` text
ctrl class の public method を追加
        ↓
Describe が検出
        ↓
client が動的に bind
        ↓
共通 Call RPC で実行
```

という流れになります。

一方、通信パターン自体を増やす場合、たとえば新しい種類の streaming
service や別種の message contract が必要な場合には protobuf
側の拡張が必要です。

------------------------------------------------------------------------

## `ese774_frame` との位置づけ

gRPC Frame は `ese774_frame` と同様に、サーバー側の制御 object
をクライアントから扱いやすくすることを目的としています。

gRPC Frame では、通常の method call に対して個別の API schema
を作るよりも、`Describe` と汎用 dispatch による透過性を優先しています。

また、`device_proxy.py` では `ese774_frame.clients.device_proxy`
と互換性を意識した entry/register API を保持しています。

------------------------------------------------------------------------

## 運用上の注意

### public method は remote API になる

制御 object の public callable は discovery
対象です。サーバー内部だけで使う method を不用意に public
にしないでください。remote API にしたくない method は `_` で始まる
private/internal name として設計する必要があります。

### property は remote method ではない

property は discovery から明示的に除外されます。これは property access
に機器 I/O や COM access などの副作用が含まれる場合に、method
列挙だけで処理が走ることを避けるためです。

remote access が必要な値は、`get_status()` のような明示的な public
method として提供する方が安全です。

### network security

現行クライアントは `grpc.insecure_channel()`
を使用します。閉じた実験ネットワーク以外で使用する場合には、TLS、認証、アクセス制御などを別途検討してください。

### API compatibility

dynamic binding により server method の追加は容易ですが、既存 method の
rename、argument の変更、return type の変更は client program
との互換性に影響します。装置制御 API として運用する場合は versioning
policy を設けることを推奨します。

------------------------------------------------------------------------

## 関連ドキュメント

Sphinx ドキュメントでは、チュートリアルおよび API reference
を参照できます。

``` text
api/modules
tutorials/grpc_intro
```

リポジトリ:

https://github.com/ohara-lab-su/grpc_frame/

------------------------------------------------------------------------

## 作者

Kengo NAKADA
