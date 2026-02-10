#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import ast
import pathlib
from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass(frozen=True)
class _Param:
    name: str
    type_str: str
    has_default: bool
    kind: str  # posonly / pos / vararg / kwonly / kwarg


@dataclass(frozen=True)
class _Method:
    name: str
    params: List[_Param]
    return_type: str


def _type_str(annotation: Optional[ast.AST]) -> str:
    if annotation is None:
        return "Any"
    try:
        return ast.unparse(annotation)
    except Exception:
        return "Any"


def _extract_method(func: ast.FunctionDef) -> _Method:
    params: List[_Param] = []

    posonly = list(func.args.posonlyargs)
    pos = list(func.args.args)
    defaults = list(func.args.defaults)

    pos_total = len(posonly) + len(pos)
    default_start = pos_total - len(defaults)
    if default_start < 0:
        default_start = 0

    idx = 0
    for arg in posonly + pos:
        if arg.arg == "self":
            idx += 1
            continue
        has_default = idx >= default_start
        kind = "posonly" if idx < len(posonly) else "pos"
        params.append(
            _Param(
                name=arg.arg,
                type_str=_type_str(arg.annotation),
                has_default=has_default,
                kind=kind,
            )
        )
        idx += 1

    if func.args.vararg is not None:
        params.append(
            _Param(
                name=func.args.vararg.arg,
                type_str=_type_str(func.args.vararg.annotation),
                has_default=False,
                kind="vararg",
            )
        )

    kwonly = list(func.args.kwonlyargs)
    kw_defaults = list(func.args.kw_defaults)
    for arg, default in zip(kwonly, kw_defaults):
        has_default = default is not None
        params.append(
            _Param(
                name=arg.arg,
                type_str=_type_str(arg.annotation),
                has_default=has_default,
                kind="kwonly",
            )
        )

    if func.args.kwarg is not None:
        params.append(
            _Param(
                name=func.args.kwarg.arg,
                type_str=_type_str(func.args.kwarg.annotation),
                has_default=False,
                kind="kwarg",
            )
        )

    if func.name == "__init__":
        return_type = "None"
    else:
        return_type = _type_str(func.returns)

    return _Method(
        name=func.name,
        params=params,
        return_type=return_type,
    )


def _parse_class(py_file: pathlib.Path, class_name: str) -> List[_Method]:
    src = py_file.read_text(encoding="utf-8")
    tree = ast.parse(src)

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            methods: List[_Method] = []
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    methods.append(_extract_method(item))
            return methods

    return []


def _fmt_method(m: _Method) -> str:
    def _fmt_param(p: _Param, prefix: str = "") -> str:
        if p.has_default:
            return f"{prefix}{p.name}: {p.type_str} = ..."
        return f"{prefix}{p.name}: {p.type_str}"

    posonly = [p for p in m.params if p.kind == "posonly"]
    pos = [p for p in m.params if p.kind == "pos"]
    vararg = next((p for p in m.params if p.kind == "vararg"), None)
    kwonly = [p for p in m.params if p.kind == "kwonly"]
    kwarg = next((p for p in m.params if p.kind == "kwarg"), None)

    args: List[str] = ["self"]

    for p in posonly:
        args.append(_fmt_param(p))
    if posonly:
        args.append("/")

    for p in pos:
        args.append(_fmt_param(p))

    if vararg is not None:
        args.append(_fmt_param(vararg, prefix="*"))

    if kwonly:
        if vararg is None:
            args.append("*")
        for p in kwonly:
            args.append(_fmt_param(p))

    if kwarg is not None:
        args.append(_fmt_param(kwarg, prefix="**"))

    sig = ", ".join(args)
    return f"    def {m.name}({sig}) -> {m.return_type}: ..."


def generate_pyi(
    *,
    class_name: str,
    ctor: _Method,
    methods: List[_Method],
) -> str:
    lines: List[str] = []
    lines.append(
        "from typing import Any, Optional, Union, Dict, List, Tuple, Callable, Sequence"
    )
    lines.append("")
    lines.append(f"class {class_name}:")
    lines.append(_fmt_method(ctor))

    seen: set[str] = set()
    for m in methods:
        if m.name.startswith("_"):
            continue
        if m.name in seen:
            continue
        seen.add(m.name)
        lines.append(_fmt_method(m))

    return "\n".join(lines)


def generate_client_pyi(
    *,
    client_py: pathlib.Path,
    client_class: str,
    ctrl_py: pathlib.Path,
    ctrl_class: str,
    base_py: Optional[pathlib.Path] = None,
    base_class: str = "GrpcClient",
    out_path: pathlib.Path,
) -> None:
    client_methods = _parse_class(client_py, client_class)
    ctrl_methods = _parse_class(ctrl_py, ctrl_class)
    base_methods = _parse_class(base_py, base_class) if base_py else []

    ctor: Optional[_Method] = None
    for m in client_methods:
        if m.name == "__init__":
            ctor = m
            break
    if ctor is None:
        raise RuntimeError(f"{client_class}.__init__ not found")

    merged: List[_Method] = []
    seen: set[str] = set()

    # 1) クライアント固有
    for m in client_methods:
        if m.name == "__init__":
            continue
        if m.name.startswith("_"):
            continue
        if m.name in seen:
            continue
        seen.add(m.name)
        merged.append(m)

    # 2) 継承元（GrpcClient）
    for m in base_methods:
        if m.name.startswith("_"):
            continue
        if m.name in seen:
            continue
        seen.add(m.name)
        merged.append(m)

    # 3) ディスパッチ元（AanddReader）
    for m in ctrl_methods:
        if m.name.startswith("_"):
            continue
        if m.name in seen:
            continue
        seen.add(m.name)
        merged.append(m)

    pyi_text = generate_pyi(
        class_name=client_class,
        ctor=ctor,
        methods=merged,
    )

    out_path.write_text(pyi_text, encoding="utf-8")
