
# gRPC Frame
---

```{toctree}
:maxdepth: 2
:caption: Contents:

api/modules
tutorials/grpc_intro
```
view on [github](https://github.com/ohara-lab-su/grpc_frame/)

---

gRPC Frame は gRPC を使った通信フレームです。
基本センスは「透過型プロキシ」であり、我々の[ese774_frame](http://github.com/ohara-lab-su/ese774_frame/)
ほぼ同じ動作をするフレームとなります。ese774_frame は pydantic/penAPI 対応と
していますが、gRPC Frame は完全透過型で、特に I/F 定義を必要としない設計に
していてるのが良くも悪くも特徴となっています。

基本コンセプトとして、
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

のように、client は server 側にある ctrl class とほぼ同型の
ctrl class を意識せずに用いることが可能です。

現在のところ、gRPC frame には ese774 frame と異なり
event 形にも対応しています。

つまり、サーバー側のイベント動作で client を動作させることが
最小の通信こととで実現されます。


# 作者
- Kengo NAKADA (中田謙吾)
  - kengo.nakada@mat.shimane-u.ac.jp
  - kengo.nakada@gmail.com
