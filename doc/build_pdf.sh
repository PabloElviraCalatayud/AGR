#!/bin/sh
# build_pdf.sh - Genera los PDF entregables a partir de las fuentes Markdown.
#
#   doc/entregables/src/*.md  ->  doc/entregables/*.pdf
#
# Requisitos: pandoc y un navegador Chromium/Chrome (impresión a PDF), o bien
# un motor LaTeX (xelatex) como alternativa. La memoria se genera en Word con
# memoria_docx.py y se convierte a PDF con LibreOffice.
#   sudo apt install pandoc chromium-browser libreoffice-writer python3-docx python3-pil
set -eu
DIR=$(cd "$(dirname "$0")" && pwd)
SRC="$DIR/entregables/src"
OUT="$DIR/entregables"
CSS="$SRC/estilo.css"
FILTRO="$SRC/include.lua"      # inserta el código de los scripts en la memoria
cd "$DIR/.."                   # raíz del repositorio: rutas de include.lua

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
    [ "$name" = memoria ] && continue      # la memoria va en Word (abajo)
    pdf="$OUT/$name.pdf"
    echo ">>> $name.md -> $(basename "$pdf")"
    if BROWSER=$(navegador); then
        html=$(mktemp --suffix=.html)
        pandoc "$md" -s --toc --toc-depth=2 --embed-resources --css "$CSS" \
            --lua-filter "$FILTRO" \
            --resource-path="$SRC:$DIR" -o "$html"
        "$BROWSER" --headless --no-sandbox --disable-gpu --no-pdf-header-footer \
            --print-to-pdf="$pdf" "file://$html" 2>/dev/null
        rm -f "$html"
    else
        pandoc "$md" --toc --lua-filter "$FILTRO" --pdf-engine=xelatex -V geometry:margin=2cm \
            --resource-path="$SRC:$DIR" -o "$pdf"
    fi
done
# Memoria: Word con el formato de la memoria de referencia y PDF desde ese Word
# (requiere python3-docx, python3-pil y LibreOffice)
echo ">>> memoria.md -> memoria.docx y memoria.pdf"
python3 "$SRC/memoria_docx.py"
echo "PDF generados en $OUT"
