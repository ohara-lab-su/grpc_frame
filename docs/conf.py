#!/usr/bin/env python
"""
Kengo NAKADA:
https://github.com/shimane-dev, https://github.com/kengo-nakada
kengo.nakada@mat.shimane-u.ac.jp, kengo.nakada@gmail.com
"""

import os, sys

sys.path.insert(0, os.path.abspath("../src"))
sys.path.insert(0, os.path.abspath("../../x_logger/src"))

project = "Project"
language = "ja"

extensions = [
    "sphinx.ext.autodoc",  # autodoc: Pythonのdocstringから自動的にAPIドキュメントを生成
    "sphinx.ext.autosummary",  # autosummary: autodocを拡張し、API一覧表や要約を自動生成
    "sphinx.ext.napoleon",  # napoleon: Google/NumpyスタイルのdocstringをSphinxが解釈できるようにする
    "sphinx.ext.viewcode",  # viewcode: ドキュメントからソースコードへのリンクを自動生成
    "sphinx.ext.intersphinx",  # Projドキュメント間のリンク
    "myst_parser",  # Markdown を有効化
]

# 対応するファイル拡張子
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}


# MyST のオプション(markdown ページ作成に必要な最小構成)
myst_enable_extensions = [
    "colon_fence",  # colon_fence: ::: を使った柔軟なフェンスブロック構文を有効化
    "deflist",  # deflist: 定義リスト（用語と説明のペア）構文をサポート
    "attrs_block",  # attrs_block: ブロック要素にクラスやIDなどの属性を付与できる
    "substitution",  # substitution: {sub} のような変数置換構文を有効化
    "linkify",  # linkify: テキスト中のURLやメールアドレスを自動的にリンク化
]
myst_linkify_fuzzy_links = True
myst_heading_anchors = 3
markdown_title = "primary"  # Markdown を確実に「ページ」として扱わせる最重要設定

# autosummary で目録ページを自動生成
autosummary_generate = True

# 型ヒント参照で失敗した時の警告を抑制する
# nitpick 無視
nitpick_ignore = [
    ("py:class", "ese774_frame.clients.async_device_client.AsyncDeviceClient"),
    ("py:class", "ese774_frame.clients.sync_device_client.SyncDeviceClient"),
    ("py:class", "ese774_frame.routers.device_router.DeviceRouter"),
    ("py:class", "x_logger.x_logger.XLogger"),
    ("py:class", "Path"),
    ("py:class", "pathlib.Path"),
    ("py:class", "direction"),
    ("py:class", "pydantic.main.BaseModel"),
    ("py:class", "ConfigDict"),
    ("py:class", "enum.Enum"),
    # 必要な型は全てここに追記
]

# 追加で推奨: 型エイリアス
autodoc_type_aliases = {
    "XLogger": "x_logger.x_logger.XLogger",
    "Path": "pathlib.Path",
    "BaseModel": "pydantic.main.BaseModel",
    "ConfigDict": "pydantic.config.ConfigDict",
    "Enum": "enum.Enum",
}

# autodoc の既定オプション：これが無いと“中身が出ない”ことがある
autodoc_default_options = {
    "members": True,
    "undoc-members": True,  # docstring が無いメンバも列挙
    "show-inheritance": True,
    # 必要に応じて:
    # "inherited-members": True,
    "private-members": True,
}

# 表示設定: 読みやすさ
add_module_names = False
autodoc_typehints = "description"
autodoc_preserve_defaults = True
set_type_checking_flag = True

# CIで重い依存が import できないならここでモック（必要に応じて追記）
autodoc_mock_imports = [
    # "torch", "opencv", "tensorflow", ...
    "win32com",
    "pythoncom",
    "x_logger",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pydantic": ("https://docs.pydantic.dev/latest/", None),
    "fastapi": ("https://fastapi.tiangolo.com/", None),
    # x_logger のようなローカル/私家版はインベントリが無いので参照解決不可
}

# テーマ
html_theme = "sphinx_rtd_theme"  # pip install sphinx-rtd-theme
# html_theme = "furo"
html_theme_options = {
    # "sidebar_hide_name": True,
    # "navigation_with_keys": True,
    "collapse_navigation": False,  # 折りたたまれず常に展開
    "navigation_depth": 4,  # 階層の深さ（toctree の maxdepth に対応）
    "titles_only": False,  # 各ページの見出しもサイドバーに表示
}
html_static_path = ["_static"]
