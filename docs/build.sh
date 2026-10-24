#!/usr/bin/env bash
set -euo pipefail

DOCS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$DOCS_DIR/.." && pwd)"
SRC_DIR="$ROOT_DIR/src"
PKG_NAME="grpc_frame"
OUTPUT_DIR="$DOCS_DIR/_build/html"

export PYTHONPATH="$SRC_DIR:${PYTHONPATH:-}"

rm -rf "$DOCS_DIR/_build" "$DOCS_DIR/en/api" "$DOCS_DIR/ja/api"

for lang in en ja; do
    mkdir -p "$DOCS_DIR/$lang/api"
    sphinx-apidoc -o "$DOCS_DIR/$lang/api" "$SRC_DIR/$PKG_NAME" -f --module-first
 done

# Build the English version at the site root and at /en/.
sphinx-build -b html -c "$DOCS_DIR" -D language=en "$DOCS_DIR/en" "$OUTPUT_DIR"
sphinx-build -b html -c "$DOCS_DIR" -D language=en "$DOCS_DIR/en" "$OUTPUT_DIR/en"
# Build the Japanese version with an independent sidebar at /ja/.
sphinx-build -b html -c "$DOCS_DIR" -D language=ja "$DOCS_DIR/ja" "$OUTPUT_DIR/ja"

echo "HTML output: $OUTPUT_DIR"
