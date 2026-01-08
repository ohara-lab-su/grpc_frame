# grpc_frame/grpc_server.py
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple, Type
import inspect
import traceback
from dataclasses import dataclass

import grpc


import grpc_frame.dispatch_core as core
from x_logger import XLogger

_logger = XLogger(log_level="debug")


@dataclass(frozen=True)
class CtrlCallPlan:
    """
    ctrl メソッド呼び出しのための実行計画を表すデータクラス。

    - args: 位置引数として渡す値のタプル
    - kwargs: キーワード引数として渡す辞書

    dispatcher 層で決定された呼び出し形式を、
    handler 側でそのまま実行するための中間表現。
    """

    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]


def request_to_positional(
    req: Any,
) -> List[Any]:
    """
    protobuf Request Message から位置引数リストを生成する。

    - フィールド番号順に値を抽出する
    - oneof フィールドは選択されているもののみを対象とする
    - repeated / message フィールドは Python オブジェクトに変換する

    Args:
        req: protobuf Request Message

    Returns:
        List[Any]: ctrl メソッドに渡す位置引数候補のリスト
    """
    _logger.debug("[request_to_positional] req =", req)

    fields: List[Any] = list(req.DESCRIPTOR.fields)
    fields.sort(key=lambda f: int(f.number))

    values: List[Any] = []
    for f in fields:
        _logger.debug(
            "[request_to_positional] field:",
            f.name,
            "number=",
            f.number,
            "oneof=",
            f.containing_oneof.name if f.containing_oneof else None,
            "label=",
            f.label,
        )
        # if f.containing_oneof is not None:
        #     continue
        if f.containing_oneof is not None:
            oneof_name: str = f.containing_oneof.name

            selected: Optional[str] = req.WhichOneof(oneof_name)
            if selected is None:
                continue
            if selected != f.name:
                continue

            raw_sel: Any = getattr(req, f.name)

            _logger.debug(
                "[request_to_positional][oneof]",
                "oneof=",
                oneof_name,
                "selected=",
                f.name,
                "raw=",
                raw_sel,
            )

            if f.label == f.LABEL_REPEATED:
                tmp_sel: List[Any] = []
                for x in raw_sel:
                    tmp_sel.append(core.protobuf_to_python(x))

                _logger.debug("[request_to_positional] append value =", tmp_sel)
                values.append(tmp_sel)
            else:
                _logger.debug("[request_to_positional] append value =", raw_sel)
                values.append(core.protobuf_to_python(raw_sel))

            continue

        raw: Any = getattr(req, f.name)

        is_repeated: bool = False
        if f.label == f.LABEL_REPEATED:
            is_repeated = True

        if is_repeated:
            tmp: List[Any] = []
            for x in raw:
                tmp.append(core.protobuf_to_python(x))
            values.append(tmp)
            continue

        values.append(core.protobuf_to_python(raw))

    _logger.debug("[request_to_positional] result values =", values)
    return values


def request_to_kwargs(
    req: Any,
) -> Dict[str, Any]:
    """
    protobuf Request Message からキーワード引数 dict を生成する。

    - フィールド名をキーとする
    - oneof フィールドは選択されているもののみを含める
    - repeated message は tuple に正規化する
    - message / scalar は protobuf_to_python で変換する

    Args:
        req: protobuf Request Message

    Returns:
        Dict[str, Any]: ctrl メソッドに渡すキーワード引数
    """
    _logger.debug(f"[DEBUG][request_to_kwargs] BEGIN")

    kwargs: Dict[str, Any] = {}

    for f in req.DESCRIPTOR.fields:
        # --- oneof 対応 ---
        if f.containing_oneof is not None:
            oneof_name: str = f.containing_oneof.name
            selected: Optional[str] = req.WhichOneof(oneof_name)

            if selected != f.name:
                continue

            raw_sel: Any = getattr(req, f.name)

            if f.label == f.LABEL_REPEATED:
                # kwargs[f.name] = [core.protobuf_to_python(x) for x in raw_sel]
                kwargs[f.name] = [_pbmsg_to_tuple(x) for x in raw_sel]
            else:
                kwargs[f.name] = core.protobuf_to_python(raw_sel)

            continue

        # --- 通常フィールド ---
        raw: Any = getattr(req, f.name)

        if f.label == f.LABEL_REPEATED:
            # kwargs[f.name] = [core.protobuf_to_python(x) for x in raw]
            kwargs[f.name] = [_pbmsg_to_tuple(x) for x in raw]
        else:
            kwargs[f.name] = core.protobuf_to_python(raw)

    return kwargs


def _has_varkw(
    sig: inspect.Signature,
) -> bool:
    """
    関数シグネチャが可変キーワード引数 (**kwargs) を持つか判定する。

    Args:
        sig (inspect.Signature): 判定対象のシグネチャ

    Returns:
        bool: **kwargs を含む場合 True
    """
    # _logger.debug(f"[DEBUG][_has_varkw]")

    for p in sig.parameters.values():
        if p.kind == p.VAR_KEYWORD:
            return True
    return False


def _pbmsg_to_tuple(
    obj: Any,
) -> Any:
    """
    protobuf Message をタプル形式に正規化する。

    用途:
    - repeated message を ctrl 側で tuple/list として扱うための変換
    - ネストした message / repeated を含む場合は dict 形式にフォールバック

    Args:
        obj: protobuf Message または任意オブジェクト

    Returns:
        Any:
            - scalar / 非 message: そのまま返す
            - 単純な message: フィールド番号順の tuple
            - 複雑な message: dict (protobuf_to_python 結果)
    """
    if not core.is_protobuf_message(obj):
        return obj

    fields: List[Any] = list(obj.DESCRIPTOR.fields)
    fields.sort(key=lambda f: int(f.number))

    out: List[Any] = []
    for f in fields:
        if f.containing_oneof is not None:
            continue
        if f.label == f.LABEL_REPEATED:
            # ネストrepeatedはここでは展開しない（従来どおり）
            return core.protobuf_to_python(obj)
        if f.message_type is not None:
            # ネストmessageもここではdictのまま（従来どおり）
            return core.protobuf_to_python(obj)

        out.append(getattr(obj, f.name))

    return tuple(out)


# ============================================================
# ctrl call planning
#   proto + signature から自動決定（従来ルール踏襲）
# ============================================================


def build_call_plan(
    ctrl_fn: Any,
    request: Any,
) -> CtrlCallPlan:
    """
    ctrl メソッドと Request Message から呼び出し計画を構築する。

    設計方針:
    - kwargs が存在する場合は positional 化しない
    - keyword-only 引数を壊さない
    - **kwargs を受け取る関数では常に kwargs 呼びにする
    - 既存の挙動（drive 等）を壊さないことを最優先する

    Args:
        ctrl_fn: 呼び出し対象の ctrl メソッド
        request: protobuf Request Message

    Returns:
        CtrlCallPlan: 実行すべき args / kwargs の組
    """
    _logger.debug(f"[DEBUG][build_call_plan]")

    sig: inspect.Signature = inspect.signature(ctrl_fn)

    params: List[inspect.Parameter] = []
    for p in sig.parameters.values():
        if p.name == "self":
            continue
        params.append(p)

    kwargs: Dict[str, Any] = request_to_kwargs(request)
    # positional: List[Any] = request_to_positional(request)

    # 追加ログ
    _logger.debug("[DEBUG][CallPlan]")
    _logger.debug("  ctrl_fn =", ctrl_fn)
    _logger.debug("  signature =", sig)
    _logger.debug("  params =", [p.name for p in params])
    # _logger.debug("  positional =", positional)
    _logger.debug("  kwargs =", kwargs)

    has_varkw: bool = _has_varkw(sig)
    _logger.debug("  has_varkw =", has_varkw)
    _logger.debug("  len(params) =", len(params))
    # _logger.debug("  len(positional) =", len(positional))

    # --- 重要 ---
    # drive(pairs, *, relative=...) のような「必須引数 + keyword-only」を壊さないため、
    # kwargs が来た場合は positional 化せず、そのまま kwargs 呼びに固定する。
    if kwargs:
        return CtrlCallPlan(args=(), kwargs=kwargs)

    if has_varkw:
        return CtrlCallPlan(args=(), kwargs=kwargs)

    if len(params) == 0:
        return CtrlCallPlan(args=(), kwargs={})

    if len(params) == len(positional):
        _logger.debug("[build_call_plan] USE positional ONLY:", positional)
        return CtrlCallPlan(args=tuple(positional), kwargs={})

    if len(params) == 1:
        _logger.debug("[build_call_plan] USE positional + oneof:", positional)
        p0: inspect.Parameter = params[0]

        # positional が1つある場合は、それをそのまま使う
        if len(positional) == 1:
            _logger.debug("[build_call_plan] USE positional == 1", positional)
            return CtrlCallPlan(args=(positional[0],), kwargs={})

        # positional が複数ある場合はまとめて1引数にする
        if len(positional) > 1:
            _logger.debug("[build_call_plan] USE positional > 1", positional)
            return CtrlCallPlan(args=(positional,), kwargs={})

        # positional が無い場合は kwargs をそのまま渡す
        return CtrlCallPlan(args=(), kwargs=kwargs)

    # positional が存在しても、kwargs に oneof（pairs 等）が含まれる場合は
    # positional を使ってはいけない
    # if len(positional) > 0:
    #     _logger.debug(
    #         "[build_call_plan] positional EXISTS but fallback to kwargs",
    #         "positional=",
    #         positional,
    #         "kwargs=",
    #         kwargs,
    #     )
    #     # return CtrlCallPlan(args=tuple(positional), kwargs=kwargs)
    #     # return CtrlCallPlan(args=(), kwargs=kwargs)
    #     return CtrlCallPlan(args=tuple(positional), kwargs={})

    return CtrlCallPlan(args=(), kwargs=kwargs)


# ----------------------
# サーバーの自動ディスパッチの心臓部分
# ----------------------


def build_dynamic_servicer_class(
    *,
    pb2: Any,
    pb2_grpc: Any,
    service_name: str,
) -> Type[Any]:
    """
    protobuf 定義と ctrl オブジェクトから動的 gRPC Servicer クラスを生成する。

    責務:
    - service 定義を走査して RPC ごとの handler を生成
    - RPC 名から ctrl メソッド名を自動対応付け
    - Request → ctrl 呼び出し → Response の流れを統一的に処理

    Args:
        pb2: *_pb2 モジュール
        pb2_grpc: *_pb2_grpc モジュール
        service_name (str): 対象サービス名

    Returns:
        Type[Any]: grpc サーバーに登録可能な Servicer クラス
    """
    service_desc: Any = pb2.DESCRIPTOR.services_by_name[service_name]
    base_cls: Any = getattr(pb2_grpc, f"{service_name}Servicer")

    class Servicer(base_cls):
        def __init__(self, *, ctrl: Any, logger: XLogger) -> None:
            """
            動的に生成される Servicer の初期化処理。

            Args:
                ctrl: 実際の制御ロジックを持つオブジェクト
                logger (XLogger): ログ出力用ロガー
            """
            self._ctrl: Any = ctrl
            self._logger: XLogger = logger

    for m in service_desc.methods:
        rpc_name: str = m.name
        ctrl_name: str = core.camel_to_snake(rpc_name)
        response_cls: Any = getattr(pb2, m.output_type.name)

        def make_handler(
            rpc_name_local: str,
            ctrl_name_local: str,
            response_cls_local: Any,
        ):
            def handler(
                self: Any,
                request: Any,
                context: Any,
            ) -> Any:
                """
                単一 RPC に対応する gRPC ハンドラ。

                処理手順:
                1. ctrl メソッドを取得
                2. Request Message から呼び出し計画を構築
                3. ctrl メソッドを args / kwargs で実行
                4. 戻り値を Response Message に変換

                例外時:
                - ctrl メソッド未実装: UNIMPLEMENTED
                - 実行時例外: INTERNAL

                Args:
                    request: protobuf Request Message
                    context: gRPC context

                Returns:
                    protobuf Response Message
                """

                self._logger.info(
                    f"[GrpcServer][DEBUG] rpc={rpc_name_local}, request={request}"
                )

                try:
                    fn: Any = getattr(self._ctrl, ctrl_name_local)
                    plan = build_call_plan(fn, request)

                    self._logger.info(
                        f"[GrpcServer][DEBUG] call plan: args={plan.args}, kwargs={plan.kwargs}"
                    )

                    if len(plan.kwargs) == 0:
                        ret = fn(*plan.args)
                    else:
                        ret = fn(*plan.args, **plan.kwargs)

                except AttributeError:
                    context.abort(
                        grpc.StatusCode.UNIMPLEMENTED,
                        f"ctrl has no method '{ctrl_name_local}'",
                    )

                except Exception as e:
                    self._logger.error(traceback.format_exc())
                    context.abort(
                        grpc.StatusCode.INTERNAL,
                        f"{rpc_name_local} failed: {e}",
                    )

                resp: Any = response_cls_local()
                return core.fill_response_message(resp, ret)

            return handler

        setattr(
            Servicer,
            rpc_name,
            make_handler(rpc_name, ctrl_name, response_cls),
        )

    return Servicer
