# README

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

        # 丸ごと差し替え
        self.get_error_count = self._get_error_count_override

    def _get_error_count_override(self) -> int:
        # RPC を呼ばない完全 override
        # return self._local_cache

        # あるいは元実装を呼ぶ
        return self._raw_get_error_count()
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
