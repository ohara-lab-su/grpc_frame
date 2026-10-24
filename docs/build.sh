#!/usr/bin/env bash
set -euo pipefail
DOCS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$DOCS_DIR/.." && pwd)"
export PYTHONPATH="$ROOT_DIR/src:${PYTHONPATH:-}"
OUT="$DOCS_DIR/_build/html"
rm -rf "$DOCS_DIR/_build" "$DOCS_DIR/_generated"
mkdir -p "$OUT" "$DOCS_DIR/_generated/en/api" "$DOCS_DIR/_generated/ja/api"
for LANG in en ja; do
    sphinx-apidoc -f --module-first -o "$DOCS_DIR/_generated/$LANG/api" "$ROOT_DIR/src/grpc_frame"
    cp -R "$DOCS_DIR/$LANG/." "$DOCS_DIR/_generated/$LANG/"
    sphinx-build -b html -c "$DOCS_DIR" -D language="$LANG" "$DOCS_DIR/_generated/$LANG" "$OUT/$LANG"
done
# The English source is also the site root; no custom HTML or redirect.
sphinx-build -b html -c "$DOCS_DIR" -D language=en "$DOCS_DIR/_generated/en" "$OUT"
