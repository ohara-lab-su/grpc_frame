# README

## v0.3.0, nakada

gRPC の役割を大きく変える。
コードを全て入れ替える。

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
- proto 側の定義は一つだ(メソッド名は呼び出し側のみ依存して、呼び出し情報は常に呼び出し側が情報を json でのせる)

### server
gRPCクライアント/サーバ

- python clinet は完全な一般の (*args, **kwargs)
- pure python xx(pos, force=force)などの形は pyi で定義する

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
