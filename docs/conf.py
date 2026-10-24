"""Shared Sphinx configuration for the independently built English/Japanese sites."""
from pathlib import Path
import sys

DOCS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DOCS_DIR.parent / "src"))

project = "grpc_frame"
root_doc = "index"
source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]
myst_enable_extensions = ["colon_fence", "deflist", "attrs_block", "substitution", "linkify"]
autosummary_generate = True
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
autodoc_typehints = "description"
# These modules are optional platform/device dependencies, not grpc_frame's API.
autodoc_mock_imports = ["win32com", "pythoncom", "x_logger"]
html_theme = "sphinx_rtd_theme"
html_theme_options = {"collapse_navigation": False, "navigation_depth": 4, "titles_only": False}
html_static_path = []
html_extra_path = []
exclude_patterns = ["_build", "_generated"]
