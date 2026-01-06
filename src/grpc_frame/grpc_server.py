#!/usr/bin/env python3
"""
Kengo NAKADA
kengo.nakada@mat.shimane-u.ac.jp
kengo.nakada@gmail.com

gRPC dynamic dispatcher (proto-driven)

- proto の service 定義から Servicer クラスを生成
- ctrl は Servicer インスタンス生成時に注入
- request -> ctrl 引数変換は「proto の情報だけ」で決定
"""

import inspect
import traceback
from typing import Any, Dict, List, Type

import grpc
from x_logger import XLogger


# ------------------------------------------------------------
# utils
# ------------------------------------------------------------


def camel_to_snake(name: str) -> str:
    """
    proto の RPC 名 (CamelCase) を python 側メソッド名 (snake_case) に寄せます。
    例: SendDpose -> send_dpose
    """
    out: List[str] = []
    for c in name:
        if c.isupper():
            out.append("_")
            out.append(c.lower())
        else:
            out.append(c)

    s = "".join(out)
    if s.startswith("_"):
        return s[1:]
    return s


def _has_varkw(sig: inspect.Signature) -> bool:
    for p in sig.parameters.values():
        if p.kind == p.VAR_KEYWORD:
            return True
    return False


def _request_fields_in_proto_order(req: Any) -> List[Any]:
    """
    repeated 1-field 構成は list をそのまま 1 要素として返す
    """
    fields = list(req.DESCRIPTOR.fields)
    fields.sort(key=lambda f: int(f.number))

    # ★ SendDpose 用：通常フィールドが1個かつ repeated
    if len(fields) == 1 and fields[0].label == fields[0].LABEL_REPEATED:
        return [list(getattr(req, fields[0].name))]

    values: List[Any] = []
    for f in fields:
        if f.containing_oneof is not None:
            continue
        values.append(getattr(req, f.name))
    return values


def request_to_kwargs(req: Any) -> Dict[str, Any]:
    """
    request を descriptor ベースで kwargs に展開します。

    - oneof は「oneof名」をキーにして、選択された submessage を値として入れます
    - 通常フィールドは field.name をキーにして値を入れます
    """
    kwargs: Dict[str, Any] = {}

    desc = req.DESCRIPTOR

    for oneof in desc.oneofs:
        selected_name = req.WhichOneof(oneof.name)
        if selected_name is None:
            continue
        kwargs[oneof.name] = getattr(req, selected_name)

    for field in desc.fields:
        if field.containing_oneof is not None:
            continue
        kwargs[field.name] = getattr(req, field.name)

    return kwargs


def call_dynamic(ctrl: Any, method: str, request: Any, kwargs: Dict[str, Any]) -> Any:
    """
    ctrl.method を完全に動的に呼びます。

    ルール（proto 由来）:
      - ctrl 側が **kwargs を受ける**なら kwargs を渡します
      - ctrl 側が **引数 0 個**なら引数なしで呼びます
      - ctrl 側が **引数 1 個**なら、request の通常フィールドを proto 順に並べて
        1個ならスカラ、複数なら list として 1引数で渡します
        （通常フィールドが 0 個の場合は oneof のみなので、kwargs から 1個を渡します）
      - ctrl 側が **引数 N 個**なら、通常フィールド数が N のとき proto 順に位置引数で渡します
      - それ以外は kwargs で呼びます
    """
    fn = getattr(ctrl, method)
    sig = inspect.signature(fn)

    param_count = len(sig.parameters)

    if param_count == 0:
        return fn()

    if _has_varkw(sig) is True:
        return fn(**kwargs)

    values = _request_fields_in_proto_order(request)
    value_count = len(values)

    # --------------------------------------------------------
    # ctrl が 1 引数のとき
    # --------------------------------------------------------
    if param_count == 1:
        if value_count == 0:
            kw_count = len(kwargs)
            if kw_count == 0:
                return fn()

            if kw_count == 1:
                return fn(next(iter(kwargs.values())))

            # proto 側は oneof だけのはずだが、ここに来たら ctrl 設計と噛み合っていない
            raise RuntimeError("cannot map request to single-arg ctrl method")

        if value_count == 1:
            return fn(values[0])

        return fn(values)

    # --------------------------------------------------------
    # ctrl が N 引数のとき（proto の通常フィールドと一致する場合は位置引数）
    # --------------------------------------------------------
    if value_count == param_count:
        return fn(*values)

    # --------------------------------------------------------
    # それ以外は kwargs（名前一致で呼べる場合に任せる）
    # --------------------------------------------------------
    return fn(**kwargs)


# ------------------------------------------------------------
# dynamic servicer factory
# ------------------------------------------------------------


def build_dynamic_servicer_class(
    *,
    pb2: Any,
    pb2_grpc: Any,
    service_name: str,
) -> Type[Any]:
    """
    proto の service 定義から、動的ディスパッチする Servicer クラスを生成して返します。
    ctrl は import 時に固定せず、Servicer インスタンス生成時に注入します。
    """
    service_desc = pb2.DESCRIPTOR.services_by_name[service_name]
    base_cls = getattr(pb2_grpc, f"{service_name}Servicer")

    class DynamicServicer(base_cls):
        def __init__(self, *, ctrl: Any, logger: XLogger):
            self._ctrl = ctrl
            self._logger = logger

    for m in service_desc.methods:
        rpc_name = m.name
        ctrl_method = camel_to_snake(rpc_name)
        res_cls = getattr(pb2, m.output_type.name)

        def make_handler(
            rpc_name_local: str,
            ctrl_method_local: str,
            res_cls_local: Any,
        ):
            def handler(self, request, context):
                try:
                    kwargs = request_to_kwargs(request)
                    ret = call_dynamic(self._ctrl, ctrl_method_local, request, kwargs)

                except AttributeError:
                    context.abort(
                        grpc.StatusCode.UNIMPLEMENTED,
                        f"ctrl has no method '{ctrl_method_local}'",
                    )

                except Exception as e:
                    self._logger.error(traceback.format_exc())
                    context.abort(
                        grpc.StatusCode.INTERNAL,
                        f"{rpc_name_local} failed: {e}",
                    )

                resp = res_cls_local()

                # --- 戻り値マッピング（proto から機械的に決める）---
                if ret is None:
                    return resp

                if isinstance(ret, dict):
                    for k, v in ret.items():
                        setattr(resp, k, v)
                    return resp

                fields = list(resp.DESCRIPTOR.fields)
                if len(fields) == 1:
                    setattr(resp, fields[0].name, ret)
                    return resp

                context.abort(
                    grpc.StatusCode.INTERNAL,
                    f"cannot map return value for {rpc_name_local}",
                )

            return handler

        setattr(
            DynamicServicer,
            rpc_name,
            make_handler(rpc_name, ctrl_method, res_cls),
        )

    return DynamicServicer
