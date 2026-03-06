# チュートリアル

このセクションでは ese774_frame の使い方を段階的に説明します。

例題として単純な制御クラス(ほぼダミー)を用意してese774 frame を使いクライアント側で
サーバー側の制御クラスを制御します。

## サーバークラスに食わせる制御クラスを用意する

```python
#!/usr/bin/env python
from typing import Any, Dict, List, Optional, Tuple


class SimpleCtrl:
    """
    フレームワークテスト用の最小 Ctrl
    - 引数/戻り値パターンの検証用
    """

    def __init__(self, name: str = "simple", logger: Optional[Any] = None):
        self._name = name
        self._counter = 0
        self._logger = logger

    # property (属性)
    @property
    def name(self) -> str:
        return self._name

    # 戻り値: str
    def ping(self) -> str:
        return "pong"

    # 引数2つ -> int
    def add(self, a: int, b: int) -> int:
        return a + b

    # 引数1つ -> str
    def echo(self, msg: str) -> str:
        return msg

    # list -> float
    def sum_list(
        self,
        values: List[float],
    ) -> float:
        return float(sum(values))

    # kwargs混在 -> dict
    def mix(
        self,
        a: int,
        b: int = 1,
        *,
        scale: float = 1.0,
        tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        val = (a + b) * scale
        return {"value": val, "tag": tag}

    # tuple 戻り
    def make_tuple(
        self,
        a: int,
        b: str,
    ) -> Tuple[int, str]:
        return (a, b)

    # dict 戻り
    def make_dict(self, key: str, value: Any) -> Dict[str, Any]:
        return {key: value}

    # Optional -> Optional
    def maybe(
        self,
        x: Optional[int] = None,
    ) -> Optional[int]:
        return x

    # None 戻り
    def set_name(
        self,
        name: str,
    ) -> None:
        self._name = name

    # 状態取得
    def get_state(self) -> Dict[str, Any]:
        self._counter += 1
        return {"name": self._name, "counter": self._counter}

    # 一般形の引数 (*args, **kwargs)
    def general(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return {"args": list(args), "kwargs": dict(kwargs)}

```

## 制御クラスをサーバーメソッドに食わせてサーバーを起動する
gRPC frame では現在のところ問答無用でサーバーがの機器制御クラスを丸ごと
クライアントで再現する完全な透過型プロキシです。ese774_frame とことなり
制御クラスの中から使用するI/Fを呈するという作業はありません。

## クライアントクラスを Frame を継承して作る

## クライアントで制御プログラムを書く