# grpc_frame/core.py
from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from x_logger import XLogger

logger = XLogger(log_level="info", logger_name="dispatch_core")

# ============================================================
# name mapping
# ============================================================


def camel_to_snake(
    name: str,
) -> str:
    """
    CamelCase / mixedCase の識別子を snake_case に変換する。

    - 大文字の直前に '_' を挿入し、小文字化する
    - 先頭が '_' になる場合は除去する
    - protobuf / RPC 名称の正規化用途を想定

    Args:
        name (str): 変換対象の識別子

    Returns:
        str: snake_case に変換された文字列
    """
    out: List[str] = []
    for ch in name:
        if ch.isupper():
            out.append("_")
            out.append(ch.lower())
        else:
            out.append(ch)

    s: str = "".join(out)
    if s.startswith("_"):
        return s[1:]
    return s


def snake_to_camel(
    name: str,
) -> str:
    """
    snake_case の識別子を CamelCase に変換する。

    - '_' 区切りで分割し、各要素の先頭を大文字化
    - 空要素は無視する
    - RPC / protobuf 名称生成用途を想定

    Args:
        name (str): snake_case の識別子

    Returns:
        str: CamelCase に変換された文字列
    """
    parts: List[str] = name.split("_")
    out: List[str] = []
    for p in parts:
        if p == "":
            continue
        head: str = p[:1].upper()
        tail: str = p[1:]
        out.append(head + tail)
    return "".join(out)


def ctrl_method_to_rpc_name(
    ctrl_method: str,
) -> str:
    """
    ctrl 側のメソッド名から RPC 名 (CamelCase) を生成する。

    - snake_case の場合は snake_to_camel を適用
    - underscore を含まない場合は先頭のみ大文字化
    - ctrl <-> protobuf RPC の自動バインド用

    Args:
        ctrl_method (str): ctrl クラス側のメソッド名

    Returns:
        str: RPC 名として使用する CamelCase 名
    """
    if ctrl_method == "":
        raise ValueError("empty ctrl_method")

    has_underscore: bool = False
    if "_" in ctrl_method:
        has_underscore = True

    if has_underscore:
        return snake_to_camel(ctrl_method)

    head: str = ctrl_method[:1].upper()
    tail: str = ctrl_method[1:]
    return head + tail


# ============================================================
# protobuf detection
# ============================================================


def is_protobuf_message(
    obj: Any,
) -> bool:
    """
    対象オブジェクトが protobuf Message インスタンスかどうかを判定する。

    判定条件:
    - DESCRIPTOR 属性を持つ
    - DESCRIPTOR.fields を持つ

    Args:
        obj (Any): 判定対象オブジェクト

    Returns:
        bool: protobuf Message であれば True
    """
    logger.debug(f"[DEBUG] is_protobuf_message")
    logger.debug(f"  obj={obj}")

    desc: Any = getattr(obj, "DESCRIPTOR", None)
    if desc is None:
        return False

    has_fields: bool = hasattr(desc, "fields")
    if not has_fields:
        return False

    return True


# ============================================================
# python -> protobuf message filling (descriptor-driven)
#   oneof input:
#     { oneof_name: { selected_field_name: value } }
# ============================================================


# ============================================================
# protobuf -> python (oneof reversible)
#   oneof: { oneof_name: { selected_field_name: value } }
# ============================================================


def protobuf_to_python(
    obj: Any,
) -> Any:
    """
    protobuf Message を Python の基本データ構造へ再帰的に変換する。

    変換規則:
    - scalar field -> 値
    - repeated field -> list
    - message field -> dict
    - oneof:
        { oneof_name: { selected_field_name: value } }

    Args:
        obj (Any): protobuf Message または任意の値

    Returns:
        Any: dict / list / scalar に変換された Python オブジェクト
    """
    logger.debug(f"[DEBUG] protobuf_to_python")
    logger.debug(f"  obj={obj}")

    if not is_protobuf_message(obj):
        return obj

    desc: Any = obj.DESCRIPTOR
    out: Dict[str, Any] = {}

    oneofs: Any = getattr(desc, "oneofs", [])
    for oneof in oneofs:
        selected: Optional[str] = obj.WhichOneof(oneof.name)
        if selected is None:
            continue
        selected_val: Any = getattr(obj, selected)
        out[oneof.name] = {selected: protobuf_to_python(selected_val)}

    for field in desc.fields:
        if field.containing_oneof is not None:
            continue

        raw: Any = getattr(obj, field.name)

        is_repeated: bool = False
        if field.label == field.LABEL_REPEATED:
            is_repeated = True

        if is_repeated:
            tmp: List[Any] = []
            for x in raw:
                tmp.append(protobuf_to_python(x))
            out[field.name] = tmp
            continue

        is_message: bool = False
        if field.message_type is not None:
            is_message = True

        if is_message:
            out[field.name] = protobuf_to_python(raw)
            continue

        out[field.name] = raw

    return out


def fill_message(
    msg: Any,
    value: Any,
) -> None:
    """
    Python オブジェクトから protobuf Message を埋めるための総合ディスパッチ関数。

    value の型に応じて以下を行う:
    - dict  : フィールド名指定による代入
    - list  : フィールド番号順による positional 代入
    - tuple : list と同様に positional 代入
    - scalar: 単一フィールド Message の場合のみ代入

    Args:
        msg (Any): protobuf Message インスタンス
        value (Any): 埋め込み元の Python オブジェクト

    Returns:
        None
    """
    logger.debug(f"[DEBUG] _fill_message_by_dict")
    logger.debug(f"  msg =", msg)
    logger.debug(f"  value", value)

    if not is_protobuf_message(msg):
        return

    if isinstance(value, dict):
        logger.debug("[fill_message] (dict):", value)
        _fill_message_by_dict(msg, value)
        return

    if isinstance(value, list):
        logger.debug("[fill_message] (list):", value)
        _fill_message_by_position(msg, value)
        return

    if isinstance(value, tuple):
        logger.debug("[fill_message] (tuple):", value)
        _fill_message_by_position(msg, list(value))
        return

    fields: List[Any] = list(msg.DESCRIPTOR.fields)
    if len(fields) != 1:
        return

    f0: Any = fields[0]

    is_repeated: bool = False
    if f0.label == f0.LABEL_REPEATED:
        is_repeated = True

    if is_repeated:
        container = getattr(msg, f0.name)
        if isinstance(value, list):
            container.extend(value)
        return

    is_msg: bool = False
    if f0.message_type is not None:
        is_msg = True

    if not is_msg:
        setattr(msg, f0.name, value)
        return

    child = getattr(msg, f0.name)
    fill_message(child, value)


def _fill_message_by_dict(
    msg: Any,
    value: Dict[str, Any],
) -> None:
    """
    dict に基づいて protobuf Message の各フィールドを設定する。

    対応内容:
    - oneof:
        - {oneof_name: {selected_field: value}}
        - oneof field 名を直接 key とする指定
    - 通常フィールド:
        - field.name -> value

    Args:
        msg (Any): protobuf Message
        value (Dict[str, Any]): フィールド名ベースの値

    Returns:
        None
    """
    logger.debug(f"[DEBUG] _fill_message_by_dict")
    logger.debug(f"  msg =", msg)
    logger.debug(f"  value", value)

    desc: Any = msg.DESCRIPTOR
    oneofs: Any = getattr(desc, "oneofs", [])

    # oneof: {oneof_name: {selected_field: val}}
    for oneof in oneofs:
        if oneof.name not in value:
            continue

        oneof_payload: Any = value[oneof.name]
        if not isinstance(oneof_payload, dict):
            continue

        if len(oneof_payload) != 1:
            continue

        selected_field_name: str = next(iter(oneof_payload.keys()))
        selected_value: Any = oneof_payload[selected_field_name]

        field_obj: Any = desc.fields_by_name.get(selected_field_name)
        if field_obj is None:
            continue

        if field_obj.containing_oneof is None:
            continue

        if field_obj.containing_oneof.name != oneof.name:
            continue

        _set_field_by_value(msg, field_obj, selected_value)

    # --- oneof field name 直接指定への対応 ---
    for field in desc.fields:
        if field.containing_oneof is None:
            continue

        if field.name not in value:
            continue

        oneof = field.containing_oneof
        selected = msg.WhichOneof(oneof.name)

        # すでに別フィールドが選択されていたら触らない
        if selected is not None and selected != field.name:
            continue

        logger.debug(
            f"[fill_message][oneof-direct] set {oneof.name}.{field.name} = {value[field.name]}"
        )
        _set_field_by_value(msg, field, value[field.name])

    # normal fields
    for key, val in value.items():
        is_oneof_key: bool = False
        for oneof in oneofs:
            if key == oneof.name:
                is_oneof_key = True
                break
        if is_oneof_key:
            continue

        field: Any = desc.fields_by_name.get(key)
        if field is None:
            continue

        # oneof field はここでは触らない（既に処理済み）
        if field.containing_oneof is not None:
            continue

        _set_field_by_value(msg, field, val)
        logger.debug(
            f"[DEBUG] _fill_message_by_dict: _set_field_by_value msg={msg}, field={field}, val={val}"
        )


def _set_field_by_value(
    msg: Any,
    field: Any,
    val: Any,
) -> None:
    """
    単一 protobuf フィールドに対して Python 値を設定する低レベル関数。

    対応:
    - repeated scalar / message
    - message field の再帰埋め込み
    - tuple は message field の positional shorthand として展開

    Args:
        msg (Any): protobuf Message
        field (Any): FieldDescriptor
        val (Any): 設定する値

    Returns:
        None
    """
    logger.debug(f"[DEBUG] _set_field_by_value")
    logger.debug(f"  field =", msg)
    logger.debug(f"  val", val)

    is_repeated: bool = False
    if field.label == field.LABEL_REPEATED:
        is_repeated = True

    if is_repeated:
        if not isinstance(val, list):
            return

        container = getattr(msg, field.name)

        is_msg: bool = False
        if field.message_type is not None:
            is_msg = True

        if not is_msg:
            container.extend(val)
            return

        for item in val:
            child = container.add()

            if isinstance(item, tuple):
                # フィールド順で dict 化
                fields = list(child.DESCRIPTOR.fields)
                fields.sort(key=lambda f: int(f.number))
                item = {f.name: v for f, v in zip(fields, item)}

            fill_message(child, item)
        return

    is_msg2: bool = False
    if field.message_type is not None:
        is_msg2 = True

    if not is_msg2:
        setattr(msg, field.name, val)
        return

    child2 = getattr(msg, field.name)
    logger.debug(
        f"[DEBUG] _set_field_by_value: fill_message, child2 ={msg}, field={field.name}, val={val}"
    )
    fill_message(child2, val)


def _fill_message_by_position(
    msg: Any,
    values: List[Any],
) -> None:
    """
    protobuf Message をフィールド番号順で positional に埋める。

    - oneof フィールドはスキップ
    - values は field.number 昇順で順次対応付け

    Args:
        msg (Any): protobuf Message
        values (List[Any]): positional 値リスト

    Returns:
        None
    """
    logger.debug(f"[DEBUG] _fill_message_by_position")
    logger.debug(f"  msg = {msg}")
    logger.debug(f"  values= {values}")

    fields: List[Any] = list(msg.DESCRIPTOR.fields)
    fields.sort(key=lambda f: int(f.number))

    index: int = 0
    for field in fields:
        if field.containing_oneof is not None:
            continue

        if index >= len(values):
            break

        v: Any = values[index]
        index += 1

        logger.debug(
            "[fill_message] set field",
            "field=",
            field.name,
            "value=",
            v,
        )

        logger.debug(
            f"[DEBUG] _fill_message_by_position, _set_field_by_value, msg={msg}, field={field}, v={v}"
        )
        _set_field_by_value(msg, field, v)


# ============================================================
# ctrl return -> response fill
# ============================================================


def fill_response_message(
    resp: Any,
    value: Any,
) -> Any:
    """
    ctrl 戻り値を protobuf Response Message に反映する。

    規則:
    - dict      -> fill_message に委譲
    - scalar    -> 単一フィールド response に代入
    - list      -> repeated フィールドに展開
    - None      -> response をそのまま返す

    Args:
        resp (Any): Response protobuf Message
        value (Any): ctrl 側の戻り値

    Returns:
        Any: 設定済み response
    """
    logger.debug(f"[DEBUG] fill_response_message")
    logger.debug(f"  resp={resp}")
    logger.debug(f"  value={value}")

    if value is None:
        return resp

    if isinstance(value, dict):
        fill_message(resp, value)
        return resp

    fields: List[Any] = list(resp.DESCRIPTOR.fields)
    if len(fields) != 1:
        return resp

    f0: Any = fields[0]

    is_repeated: bool = False
    if f0.label == f0.LABEL_REPEATED:
        is_repeated = True

    if is_repeated:
        container = getattr(resp, f0.name)
        if isinstance(value, list):
            container.extend(value)
        return resp

    is_msg: bool = False
    if f0.message_type is not None:
        is_msg = True

    if not is_msg:
        setattr(resp, f0.name, value)
        return resp

    child = getattr(resp, f0.name)
    fill_message(child, value)
    return resp


def unwrap_response(
    resp: Any,
) -> Any:
    """
    protobuf Response Message を Python 値へ展開する。

    規則:
    - ok フィールドを持つ場合は bool を返す
    - それ以外は protobuf_to_python により dict 化

    Args:
        resp (Any): protobuf Response Message または任意の値

    Returns:
        Any: bool / dict / scalar
    """
    if not is_protobuf_message(resp):
        return resp

    has_ok: bool = hasattr(resp, "ok")
    if has_ok:
        ok_val: Any = getattr(resp, "ok")
        return bool(ok_val)

    return protobuf_to_python(resp)
