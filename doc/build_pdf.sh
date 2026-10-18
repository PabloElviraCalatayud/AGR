#!/bin/sh
# build_pdf.sh - Genera los PDF entregables a partir de las fuentes Markdown.
#
#   doc/entregables/src/*.md  ->  doc/entregables/*.pdf
#
# Requisitos: pandoc y un navegador Chromium/Chrome (impresión a PDF), o bien
# un motor LaTeX (xelatex) como alternativa.
#   sudo apt install pandoc chromium-browser   # o: texlive-xetex
set -eu
DIR=$(cd "$(dirname "$0")" && pwd)
SRC="$DIR/entregables/src"
OUT="$DIR/entregables"
CSS="$SRC/estilo.css"

navegador() {
    for b in chromium chromium-browser google-chrome google-chrome-stable \
             /opt/pw-browsers/chromium-*/chrome-linux/chrome; do
        command -v "$b" >/dev/null 2>&1 && { command -v "$b"; return 0; }
        [ -x "$b" ] && { echo "$b"; return 0; }
    done
    return 1
}

for md in "$SRC"/*.md; do
    name=$(basename "$md" .md)
    pdf="$OUT/$name.pdf"
    echo ">>> $name.md -> $(basename "$pdf")"
    if BROWSER=$(navegador); then
        html=$(mktemp --suffix=.html)
        pandoc "$md" -s --toc --toc-depth=2 --embed-resources --css "$CSS" \
            --resource-path="$SRC:$DIR" -o "$html"
        "$BROWSER" --headless --no-sandbox --disable-gpu --no-pdf-header-footer \
            --print-to-pdf="$pdf" "file://$html" 2>/dev/null
        rm -f "$html"
    else
        pandoc "$md" --toc --pdf-engine=xelatex -V geometry:margin=2cm \
            --resource-path="$SRC:$DIR" -o "$pdf"
    fi
done
echo "PDF generados en $OUT"
