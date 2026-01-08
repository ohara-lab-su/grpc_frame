# grpc_frame/core.py
from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from x_logger import XLogger

logger = XLogger(log_level="debug")

# ============================================================
# name mapping
# ============================================================


def camel_to_snake(
    name: str,
) -> str:
    """

    Args:
        name:

    Returns:

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

    Args:
        name:

    Returns:

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

    Args:
        ctrl_method:

    Returns:

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

    Args:
        obj:

    Returns:

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


def fill_message(
    msg: Any,
    value: Any,
) -> None:
    """

    Args:
        msg:
        value:

    Returns:

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

    Args:
        msg:
        value:

    Returns:

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
        # if field.containing_oneof is not None:
        #     continue

        logger.debug(
            f"[DEBUG] _fill_message_by_dict: _set_field_by_value msg={msg}, field={field}, val={val}"
        )
        _set_field_by_value(msg, field, val)


def _set_field_by_value(
    msg: Any,
    field: Any,
    val: Any,
) -> None:
    """

    Args:
        msg:
        field:
        val:

    Returns:

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

    Args:
        msg:
        values:

    Returns:

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

    Args:
        resp:
        value:

    Returns:

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

    Args:
        resp:

    Returns:

    """
    if not is_protobuf_message(resp):
        return resp

    has_ok: bool = hasattr(resp, "ok")
    if has_ok:
        ok_val: Any = getattr(resp, "ok")
        return bool(ok_val)

    return protobuf_to_python(resp)
