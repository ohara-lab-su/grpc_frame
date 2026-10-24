#!/usr/bin/env bash
set -euo pipefail

DOCS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$DOCS_DIR/.." && pwd)"
PACKAGE_DIR="$ROOT_DIR/src/grpc_frame"
STAGE_DIR="$DOCS_DIR/_generated"
BUILD_DIR="$DOCS_DIR/_build"
HTML_DIR="$BUILD_DIR/html"

if [[ ! -d "$PACKAGE_DIR" ]]; then
    echo "ERROR: grpc_frame package not found: $PACKAGE_DIR" >&2
    exit 1
fi

export PYTHONPATH="$ROOT_DIR/src:${PYTHONPATH:-}"
rm -rf "$STAGE_DIR" "$BUILD_DIR"
mkdir -p "$STAGE_DIR" "$HTML_DIR"

for lang in en ja; do
    source_dir="$DOCS_DIR/$lang"
    stage_dir="$STAGE_DIR/$lang"
    if [[ ! -f "$source_dir/index.md" || ! -f "$source_dir/api/index.md" ]]; then
        echo "ERROR: missing language index or API index: $lang" >&2
        exit 1
    fi
    mkdir -p "$stage_dir"
    cp -R "$source_dir/." "$stage_dir/"
    sphinx-apidoc --force --module-first -o "$stage_dir/api" "$PACKAGE_DIR"
    if [[ ! -f "$stage_dir/api/modules.rst" ]]; then
        echo "ERROR: API index not generated: $lang" >&2
        exit 1
    fi
done

# Root and /en/ are both the English documentation, never a language selector.
sphinx-build -b html -c "$DOCS_DIR" -d "$BUILD_DIR/doctrees/root" -D language=en "$STAGE_DIR/en" "$HTML_DIR"
sphinx-build -b html -c "$DOCS_DIR" -d "$BUILD_DIR/doctrees/en" -D language=en "$STAGE_DIR/en" "$HTML_DIR/en"
sphinx-build -b html -c "$DOCS_DIR" -d "$BUILD_DIR/doctrees/ja" -D language=ja "$STAGE_DIR/ja" "$HTML_DIR/ja"

for page in     "$HTML_DIR/index.html"     "$HTML_DIR/api/modules.html"     "$HTML_DIR/tutorials/grpc_intro.html"     "$HTML_DIR/tutorials/advanced.html"     "$HTML_DIR/en/index.html"     "$HTML_DIR/en/api/modules.html"     "$HTML_DIR/ja/index.html"     "$HTML_DIR/ja/api/modules.html"     "$HTML_DIR/ja/tutorials/grpc_intro.html"     "$HTML_DIR/ja/tutorials/advanced.html"; do
    if [[ ! -s "$page" ]]; then
        echo "ERROR: missing or empty generated page: $page" >&2
        exit 1
    fi
done

touch "$HTML_DIR/.nojekyll"
echo "Pages built: $HTML_DIR"
