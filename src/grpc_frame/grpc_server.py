#!/usr/bin/env python3
"""
Kengo NAKADA
kengo.nakada@mat.shimane-u.ac.jp
kengo.nakada@gmail.com

gRPC dynamic dispatcher (proto-driven)

- proto の service 定義から Servicer クラスを生成
- ctrl は Servicer インスタンス生成時に注入
- request -> ctrl 引数変換は「proto の情報だけ」で決定
- ctrl へ protobuf message を渡さない（必ず python 値へ変換して渡す）
"""

import inspect
import traceback
from typing import Any, Dict, List, Type, Optional

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


def _is_protobuf_message(obj: Any) -> bool:
    desc = getattr(obj, "DESCRIPTOR", None)
    if desc is None:
        return False
    fields = getattr(desc, "fields", None)
    if fields is None:
        return False
    return True


def _protobuf_to_python(obj: Any) -> Any:
    """
    ctrl に渡す前に、protobuf message / repeated container を純 python に落とす。
    - message -> dict（フィールド名: 値）または oneof は oneof名: dict
    - repeated -> list
    - scalar -> scalar
    """
    if _is_protobuf_message(obj) is False:
        return obj

    out: Dict[str, Any] = {}

    desc = obj.DESCRIPTOR

    for oneof in desc.oneofs:
        selected_name = obj.WhichOneof(oneof.name)
        if selected_name is None:
            continue
        selected_val = getattr(obj, selected_name)
        out[oneof.name] = _protobuf_to_python(selected_val)

    for field in desc.fields:
        if field.containing_oneof is not None:
            continue

        val = getattr(obj, field.name)

        if field.label == field.LABEL_REPEATED:
            tmp: List[Any] = []
            for x in val:
                tmp.append(_protobuf_to_python(x))
            out[field.name] = tmp
            continue

        if field.message_type is not None:
            out[field.name] = _protobuf_to_python(val)
            continue

        out[field.name] = val

    return out


def _request_fields_in_proto_order_python(req: Any) -> List[Any]:
    """
    request の「通常フィールド（oneof を除く）」を proto 番号順に python 値で返す
    repeated 1-field 構成は list をそのまま 1 要素として返す
    """
    fields = list(req.DESCRIPTOR.fields)
    fields.sort(key=lambda f: int(f.number))

    if len(fields) == 1:
        f0 = fields[0]
        if f0.label == f0.LABEL_REPEATED:
            return [list(getattr(req, f0.name))]

    values: List[Any] = []
    for f in fields:
        if f.containing_oneof is not None:
            continue
        raw = getattr(req, f.name)
        values.append(_protobuf_to_python(raw))
    return values


def request_to_kwargs_python(req: Any) -> Dict[str, Any]:
    """
    request を descriptor ベースで kwargs に展開（ctrl へは python 値のみ渡す）。

    - oneof は「oneof名」をキーにして、選択された submessage を python 値として入れる
    - 通常フィールドは field.name をキーにして python 値として入れる
    """
    kwargs: Dict[str, Any] = {}
    desc = req.DESCRIPTOR

    for oneof in desc.oneofs:
        selected_name = req.WhichOneof(oneof.name)
        if selected_name is None:
            continue
        selected_val = getattr(req, selected_name)
        kwargs[oneof.name] = _protobuf_to_python(selected_val)

    for field in desc.fields:
        if field.containing_oneof is not None:
            continue
        raw = getattr(req, field.name)
        kwargs[field.name] = _protobuf_to_python(raw)

    return kwargs


def call_dynamic(ctrl: Any, method: str, request: Any, kwargs: Dict[str, Any]) -> Any:
    """
    ctrl.method を完全に動的に呼びます（ctrl へは python 値のみ）。

    ルール（proto 由来）:
      - ctrl 側が **kwargs を受ける**なら kwargs を渡す
      - ctrl 側が 引数 0 個 なら引数なし
      - ctrl 側が 引数 1 個 なら、通常フィールドを proto 順に並べて
        1個ならスカラ、複数なら list を 1 引数で渡す
        （通常フィールドが 0 個の場合は oneof のみなので、kwargs から 1個を渡す）
      - ctrl 側が 引数 N 個 なら、通常フィールド数が N のとき proto 順に位置引数で渡す
      - それ以外は kwargs
    """
    fn = getattr(ctrl, method)
    sig = inspect.signature(fn)

    param_count = len(sig.parameters)

    if param_count == 0:
        return fn()

    if _has_varkw(sig) is True:
        return fn(**kwargs)

    values = _request_fields_in_proto_order_python(request)
    value_count = len(values)

    if param_count == 1:
        if value_count == 0:
            kw_count = len(kwargs)
            if kw_count == 0:
                return fn()

            if kw_count == 1:
                return fn(next(iter(kwargs.values())))

            raise RuntimeError("cannot map request to single-arg ctrl method")

        if value_count == 1:
            return fn(values[0])

        return fn(values)

    if value_count == param_count:
        return fn(*values)

    return fn(**kwargs)


def _fill_message_in_proto_order(msg: Any, value: Any) -> None:
    """
    message フィールドに python 値を流し込む。
    - value が dict: 名前でセット（submessage は再帰）
    - value が list/tuple: proto 番号順にセット
    - value が scalar: message が 1 フィールドのときだけセット
    """
    if isinstance(value, dict):
        for k, v in value.items():
            field = msg.DESCRIPTOR.fields_by_name.get(k)
            if field is None:
                continue

            if field.label == field.LABEL_REPEATED:
                container = getattr(msg, k)
                if isinstance(v, list) is False:
                    continue

                if field.message_type is None:
                    container.extend(v)
                    continue

                for item in v:
                    child = container.add()
                    _fill_message_in_proto_order(child, item)
                continue

            if field.message_type is None:
                setattr(msg, k, v)
                continue

            child_msg = getattr(msg, k)
            _fill_message_in_proto_order(child_msg, v)
        return

    if isinstance(value, (list, tuple)):
        fields = list(msg.DESCRIPTOR.fields)
        fields.sort(key=lambda f: int(f.number))

        idx = 0
        for f in fields:
            if f.containing_oneof is not None:
                continue
            if idx >= len(value):
                break

            v = value[idx]
            idx += 1

            if f.label == f.LABEL_REPEATED:
                container = getattr(msg, f.name)
                if isinstance(v, list) is False:
                    continue

                if f.message_type is None:
                    container.extend(v)
                    continue

                for item in v:
                    child = container.add()
                    _fill_message_in_proto_order(child, item)
                continue

            if f.message_type is None:
                setattr(msg, f.name, v)
                continue

            child_msg = getattr(msg, f.name)
            _fill_message_in_proto_order(child_msg, v)
        return

    fields = list(msg.DESCRIPTOR.fields)
    if len(fields) != 1:
        return

    f0 = fields[0]
    if f0.label == f0.LABEL_REPEATED:
        container = getattr(msg, f0.name)
        if isinstance(value, list):
            container.extend(value)
        return

    if f0.message_type is None:
        setattr(msg, f0.name, value)
        return

    child_msg = getattr(msg, f0.name)
    _fill_message_in_proto_order(child_msg, value)


def _map_return_to_response(resp: Any, ret: Any) -> Any:
    """
    ctrl の戻り値(ret: python) を response protobuf にマッピングする。
    message フィールドへは代入せず、サブフィールド埋めを行う。
    """
    if ret is None:
        return resp

    if isinstance(ret, dict):
        for k, v in ret.items():
            field = resp.DESCRIPTOR.fields_by_name.get(k)
            if field is None:
                continue

            if field.label == field.LABEL_REPEATED:
                container = getattr(resp, k)
                if isinstance(v, list) is False:
                    continue

                if field.message_type is None:
                    container.extend(v)
                    continue

                for item in v:
                    child = container.add()
                    _fill_message_in_proto_order(child, item)
                continue

            if field.message_type is None:
                setattr(resp, k, v)
                continue

            child_msg = getattr(resp, k)
            _fill_message_in_proto_order(child_msg, v)

        return resp

    fields = list(resp.DESCRIPTOR.fields)

    if len(fields) == 1:
        f0 = fields[0]

        if f0.label == f0.LABEL_REPEATED:
            container = getattr(resp, f0.name)
            if isinstance(ret, list):
                container.extend(ret)
            return resp

        if f0.message_type is None:
            setattr(resp, f0.name, ret)
            return resp

        child_msg = getattr(resp, f0.name)
        _fill_message_in_proto_order(child_msg, ret)
        return resp

    return None


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
                    kwargs = request_to_kwargs_python(request)
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

                mapped = _map_return_to_response(resp, ret)
                if mapped is not None:
                    return mapped

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