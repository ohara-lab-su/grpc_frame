"""
K.NAKADA, kengo.nakada@gmail.com, kengo.nakada@mat.shimane-u.ac.jp
"""

from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any, Dict, List, Optional, Tuple, Type


# ============================================================
# name mapping
# ============================================================


def snake_to_camel(
    name: str,
) -> str:
    """
    snake_case の文字列を CamelCase へ変換

    仕様:
    - "_" で split し、各要素の先頭 1 文字を大文字化して連結
    - 連続する "_" による空要素は無視

    例:
    - "move_pose" -> "MovePose"
    - "move__pose" -> "MovePose"
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


def camel_to_snake(
    name: str,
) -> str:
    """
    CamelCase / PascalCase 風の文字列を snake_case へ変換

    仕様:
    - 大文字の直前に "_" を挿入し、小文字化
    - 先頭が "_" になった場合は 1 文字だけ除去（例: "Foo" -> "foo"）。
    - 既存の "_" はそのまま残る（厳密な正規化は行わない）。

    例:
    - "MovePose" -> "move_pose"
    - "movePose" -> "move_pose"
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


def ctrl_method_to_rpc_name(
    ctrl_method: str,
) -> str:
    """
    ctrl 側メソッド名から、gRPC の RPC 名へ変換

    変換ルール（従来仕様踏襲）:
    - ctrl_method が snake_case の場合: snake_to_camel(ctrl_method)
    - ctrl_method が lowerCamelCase など "_" を含まない場合:
      先頭 1 文字だけ大文字化して連結（例: "takeArm" -> "TakeArm"）

    注意:
    - 空文字は ValueError
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
    与えられたオブジェクトが protobuf message らしいかを判定

    判定条件（軽量・保守的）:
    - obj.DESCRIPTOR が存在
    - DESCRIPTOR.fields が存在

    目的:
    - protobuf_to_python / fill_message 系で、message と素の python 値を分岐するため。
    """
    desc: Any = getattr(obj, "DESCRIPTOR", None)
    if desc is None:
        return False

    has_fields: bool = hasattr(desc, "fields")
    if not has_fields:
        return False

    return True


# ============================================================
# protobuf -> python (oneof reversible)
#   oneof: { oneof_name: { selected_field_name: value } }
# ============================================================


def protobuf_to_python(obj: Any) -> Any:
    """
    protobuf message を Python のネイティブ構造へ変換（oneof を可逆表現で保持）。

    変換方針:
    - oneof は次の形で out に格納します（可逆性を優先）:
        { oneof_name: { selected_field_name: converted_value } }
    - 通常フィールドは field.name を key として格納する
    - repeated は list へ展開する
    - message 型は再帰する
    - scalar はそのまま格納する

    注意:
    - oneof に属するフィールドは「通常フィールド側」では処理しない
    """
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


def request_to_kwargs(
    req: Any,
) -> Dict[str, Any]:
    """
    request(message) から、ctrl 呼び出し用の kwargs 辞書へ変換する

    方針:
    - oneof は protobuf_to_python と同じ可逆表現で kwargs に入れる:
        kwargs[oneof_name] = { selected_field_name: converted_value }
    - それ以外のフィールドは kwargs[field.name] = converted_value
    - oneof に属するフィールドは通常フィールド側では処理しない

    用途:
    - build_call_plan() が、ctrl 関数シグネチャに応じた渡し方を決めるための材料。
    """
    desc: Any = req.DESCRIPTOR
    kwargs: Dict[str, Any] = {}

    oneofs: Any = getattr(desc, "oneofs", [])
    for oneof in oneofs:
        selected: Optional[str] = req.WhichOneof(oneof.name)
        if selected is None:
            continue
        kwargs[oneof.name] = {selected: protobuf_to_python(getattr(req, selected))}

    for field in desc.fields:
        if field.containing_oneof is not None:
            continue
        kwargs[field.name] = protobuf_to_python(getattr(req, field.name))

    return kwargs


def request_to_positional(
    req: Any,
) -> List[Any]:
    """
    request(message) を、フィールド番号順の positional list へ変換

    方針:
    - req.DESCRIPTOR.fields を field.number 昇順に並べる
    - oneof に属するフィールドはスキップ
    - repeated は list 化（要素は再帰変換）。
    - message は再帰変換

    用途:
    - build_call_plan() が「引数個数が一致する」ケースで位置引数に載せるため。
    """
    fields: List[Any] = list(req.DESCRIPTOR.fields)
    fields.sort(key=lambda f: int(f.number))

    values: List[Any] = []
    for f in fields:
        if f.containing_oneof is not None:
            continue

        raw: Any = getattr(req, f.name)

        is_repeated: bool = False
        if f.label == f.LABEL_REPEATED:
            is_repeated = True

        if is_repeated:
            tmp: List[Any] = []
            for x in raw:
                tmp.append(protobuf_to_python(x))
            values.append(tmp)
            continue

        values.append(protobuf_to_python(raw))

    return values


# ============================================================
# ctrl call planning
#   proto + signature から自動決定（従来ルール踏襲）
# ============================================================


@dataclass(frozen=True)
class CtrlCallPlan:
    """
    ctrl 関数呼び出しの「実際に渡す args/kwargs」を保持

    - args: 位置引数タプル
    - kwargs: キーワード引数辞書

    build_call_plan() を生成
    """

    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]


def _has_varkw(
    sig: inspect.Signature,
) -> bool:
    """
    inspect.Signature に **kwargs（VAR_KEYWORD）が含まれるかを判定

    用途:
    - build_call_plan() が「kwargs をそのまま渡せる関数か」を判断
    """
    for p in sig.parameters.values():
        if p.kind == p.VAR_KEYWORD:
            return True
    return False


def build_call_plan(
    ctrl_fn: Any,
    request: Any,
) -> CtrlCallPlan:
    """
    ctrl 関数と request(message) から、呼び出し方法（args/kwargs）を自動決定

    入力:
    - ctrl_fn: ctrl 側のメソッド（bound method でも function でも可）
    - request: protobuf request message

    生成材料:
    - kwargs: request_to_kwargs(request)
    - positional: request_to_positional(request)  ※ field.number 順

    決定ロジック（従来ルール踏襲）:
    1) ctrl_fn が **kwargs を受ける場合:
       - args=() / kwargs=kwargs
    2) ctrl_fn が引数 0 個（self 以外が無い）:
       - args=() / kwargs={}
    3) ctrl_fn の引数数 == positional の要素数:
       - args=tuple(positional) / kwargs={}
    4) ctrl_fn の引数が 1 個の場合:
       - request が空なら空呼び出し
       - kwargs が 1 要素なら、その値だけを単一引数として渡す
       - positional が 1 要素なら、それを単一引数として渡す
       - それ以外は「list(positional) を 1 引数」として渡す
    5) それ以外:
       - args=() / kwargs=kwargs

    戻り値:
    - CtrlCallPlan(args, kwargs)
    """
    sig: inspect.Signature = inspect.signature(ctrl_fn)

    params: List[inspect.Parameter] = []
    for p in sig.parameters.values():
        if p.name == "self":
            continue
        params.append(p)

    kwargs: Dict[str, Any] = request_to_kwargs(request)
    positional: List[Any] = request_to_positional(request)

    has_varkw: bool = _has_varkw(sig)
    if has_varkw:
        return CtrlCallPlan(args=(), kwargs=kwargs)

    if len(params) == 0:
        return CtrlCallPlan(args=(), kwargs={})

    if len(params) == len(positional):
        return CtrlCallPlan(args=tuple(positional), kwargs={})

    if len(params) == 1:
        if len(positional) == 0:
            if len(kwargs) == 0:
                return CtrlCallPlan(args=(), kwargs={})
            if len(kwargs) == 1:
                only_val: Any = next(iter(kwargs.values()))
                return CtrlCallPlan(args=(only_val,), kwargs={})
            return CtrlCallPlan(args=(), kwargs=kwargs)

        if len(positional) == 1:
            return CtrlCallPlan(args=(positional[0],), kwargs={})

        return CtrlCallPlan(args=(positional,), kwargs={})

    return CtrlCallPlan(args=(), kwargs=kwargs)


# ============================================================
# python -> protobuf message filling (descriptor-driven)
#   oneof input:
#     { oneof_name: { selected_field_name: value } }
# ============================================================


def fill_message(
    msg: Any,
    value: Any,
) -> None:
    """
    python 値（dict/list/scalar）から protobuf message を descriptor 駆動で埋める

    入力 value の解釈:
    - dict:
        - 通常フィールド: { field_name: value }
        - oneof: { oneof_name: { selected_field_name: value } }  ※可逆表現
      → _fill_message_by_dict(msg, value)
    - list / tuple:
        - field.number 順に、oneof を除いた通常フィールドへ順番に割り当て
      → _fill_message_by_position(msg, values)
    - scalar:
        - msg が「フィールド 1 個だけ」のときのみ、そのフィールドへ代入（単純ケース）

    注意:
    - msg が protobuf message でない場合は何もしない
    - 型不一致や想定外の形は、黙って無視する分岐が含まれる（例: repeated に list 以外）。
    """
    if not is_protobuf_message(msg):
        return

    if isinstance(value, dict):
        _fill_message_by_dict(msg, value)
        return

    if isinstance(value, list):
        _fill_message_by_position(msg, value)
        return

    if isinstance(value, tuple):
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
    dict 形式の入力から protobuf message を埋める

    対応する dict 形式:
    1) oneof:
        { oneof_name: { selected_field_name: val } }
       - selected_field_name が実在し、その field が oneof に属している場合のみ反映
    2) 通常フィールド:
        { field_name: val }
       - oneof 自体のキー（oneof.name）は通常フィールドとしては扱わない

    実際の代入は _set_field_by_value() に委譲
    """
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
        if field.containing_oneof is not None:
            continue

        _set_field_by_value(msg, field, val)


def _set_field_by_value(
    msg: Any,
    field: Any,
    val: Any,
) -> None:
    """
    descriptor の Field と python 値から、msg の該当フィールドへ値を設定

    対応:
    - repeated:
        - scalar repeated: container.extend(list)
        - message repeated: container.add() して各要素を fill_message で再帰
    - non-repeated:
        - scalar: setattr(msg, field.name, val)
        - message: child=msg.field; fill_message(child, val)

    注意:
    - repeated に list 以外が来た場合は何もしません（黙って return）。
    """
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
            fill_message(child, item)
        return

    is_msg2: bool = False
    if field.message_type is not None:
        is_msg2 = True

    if not is_msg2:
        setattr(msg, field.name, val)
        return

    child2 = getattr(msg, field.name)
    fill_message(child2, val)


def _fill_message_by_position(
    msg: Any,
    values: List[Any],
) -> None:
    """
    list（位置引数相当）から protobuf message を埋める

    仕様:
    - msg.DESCRIPTOR.fields を field.number 昇順に処理
    - oneof に属するフィールドはスキップ
    - values を先頭から順に対応付け、_set_field_by_value() で代入
    - values が尽きたら終了
    """
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

        _set_field_by_value(msg, field, v)


def build_request_message(
    request_cls: Type[Any],
    kwargs: Dict[str, Any],
) -> Any:
    """
    request_cls から request message を生成します。

    手順:
    1) まず request_cls(**kwargs) を試す（生成子が受けられる形なら最短）
    2) 失敗した場合は request_cls() で空インスタンスを作り、
       fill_message(req, kwargs) で descriptor 駆動充填する

    戻り値:
    - 生成した request message
    """
    try:
        return request_cls(**kwargs)
    except Exception:
        pass

    req: Any = request_cls()
    fill_message(req, kwargs)
    return req


# ============================================================
# ctrl return -> response fill
# ============================================================


def fill_response_message(
    resp: Any,
    value: Any,
) -> Any:
    """
    ctrl の戻り値 value を、protobuf response message resp へ詰める

    対応:
    - value が None:
        - resp をそのまま返す（何も詰めない）
    - value が dict:
        - fill_message(resp, value) で埋める
    - resp が「フィールド 1 個だけ」の場合:
        - repeated なら list を extend
        - scalar なら setattr
        - message なら子 message に fill_message

    目的:
    - ctrl 側の戻り値が bool / scalar / dict / list 等でも、response を最小規則で埋める。
    """
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
    protobuf response message から、呼び出し側が使いやすい形へ展開します。

    ルール:
    - resp が protobuf message でない場合: resp をそのまま返す
    - resp に ok フィールドがある場合: bool(resp.ok) を返す（成功可否を最優先）
    - それ以外: protobuf_to_python(resp) を返す（oneof を可逆表現で保持）

    注意:
    - ok の有無だけで処理が分岐するため、response 設計側の規約が重要
    """
    if not is_protobuf_message(resp):
        return resp

    has_ok: bool = hasattr(resp, "ok")
    if has_ok:
        ok_val: Any = getattr(resp, "ok")
        return bool(ok_val)

    return protobuf_to_python(resp)
