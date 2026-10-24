#!/usr/bin/env bash
set -euo pipefail

DOCS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$DOCS_DIR/.." && pwd)"
SOURCE_DIR="$ROOT_DIR/src/grpc_frame"
STAGE_DIR="$DOCS_DIR/_generated"
OUTPUT_DIR="$DOCS_DIR/_build/html"

if [[ ! -d "$SOURCE_DIR" ]]; then
    echo "ERROR: grpc_frame source package not found: $SOURCE_DIR" >&2
    exit 1
fi

export PYTHONPATH="$ROOT_DIR/src:${PYTHONPATH:-}"
rm -rf "$STAGE_DIR" "$DOCS_DIR/_build"
mkdir -p "$OUTPUT_DIR"

for lang in en ja; do
    mkdir -p "$STAGE_DIR/$lang"
    cp -R "$DOCS_DIR/$lang/." "$STAGE_DIR/$lang/"
    sphinx-apidoc --force --module-first -o "$STAGE_DIR/$lang/api" "$SOURCE_DIR"
    if [[ ! -f "$STAGE_DIR/$lang/api/modules.rst" ]]; then
        echo "ERROR: sphinx-apidoc did not generate api/modules.rst ($lang)" >&2
        exit 1
    fi
done

# Build the root first, so the English index is the actual site index.
sphinx-build -b html -c "$DOCS_DIR" -D language=en "$STAGE_DIR/en" "$OUTPUT_DIR"
sphinx-build -b html -c "$DOCS_DIR" -D language=en "$STAGE_DIR/en" "$OUTPUT_DIR/en"
sphinx-build -b html -c "$DOCS_DIR" -D language=ja "$STAGE_DIR/ja" "$OUTPUT_DIR/ja"

for page in "$OUTPUT_DIR/index.html" "$OUTPUT_DIR/en/index.html" "$OUTPUT_DIR/ja/index.html" "$OUTPUT_DIR/en/api/modules.html" "$OUTPUT_DIR/ja/api/modules.html"; do
    if [[ ! -f "$page" ]]; then
        echo "ERROR: expected HTML page is missing: $page" >&2
        exit 1
    fi
done
printf 'Generated multilingual documentation: %s\n' "$OUTPUT_DIR"
