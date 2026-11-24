#!/usr/bin/env python3
"""
memoria_docx.py - Genera la memoria en Word (y PDF) con el formato de la
memoria de referencia: plantilla_memoria.docx aporta los estilos, las fuentes
(Lora y Marcellus), las numeraciones y los pies de página.

  python3 doc/entregables/src/memoria_docx.py            # memoria.docx y memoria.pdf

Fuente: memoria.md (Markdown de pandoc). Correspondencia de elementos:
  YAML titulo / subtitulo / subtitulo2 / participantes   portada
  # Sección                     título numerado (1., 2., ...) en página nueva
  ## Apartado                   apartado numerado (1., 2., ...) en Lora
  ### Punto                     punto con letra (a., b., ...) en Marcellus
  párrafo                       Lora 11 justificado + línea en blanco
  lista de viñetas              líneas con sangría de primera línea (sin viñeta)
  ```{titulo="f"} ... ```       cuadro de código (Courier New 10) con título
  ```{include="ruta"} ```       ídem con el contenido del fichero (include.lua)
  ![](imagen){width="60%"}      imagen centrada (por defecto, todo el ancho)
  tabla                         tabla con bordes negros en Lora 10

El índice lleva el número de página de cada sección: se genera el PDF una vez,
se buscan las páginas y se vuelve a generar con ellas.
Requisitos: pandoc, python3-docx, Pillow y LibreOffice (soffice) para el PDF.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Emu

SRC = Path(__file__).resolve().parent              # doc/entregables/src
RAIZ = SRC.parents[2]                              # raíz del repositorio
SALIDA = SRC.parent                                # doc/entregables
ANCHO = 9029                                       # ancho del texto (twips)
NS = nsdecls("w", "r")

LORA, MARC, MONO = "Lora", "Marcellus", "Courier New"


# --------------------------------------------------------------------------
# XML de Word
# --------------------------------------------------------------------------
def rpr(fuente=LORA, b=False, i=False, color=None, sz=None, u=False):
    x = (f'<w:rFonts w:ascii="{fuente}" w:cs="{fuente}" '
         f'w:eastAsia="{fuente}" w:hAnsi="{fuente}"/>')
    if b:
        x += '<w:b w:val="1"/><w:bCs w:val="1"/>'
    if i:
        x += '<w:i w:val="1"/><w:iCs w:val="1"/>'
    if color:
        x += f'<w:color w:val="{color}"/>'
    if sz:
        x += f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>'
    if u:
        x += '<w:u w:val="single"/>'
    return f"<w:rPr>{x}</w:rPr>"


def run(texto, **fmt):
    partes = texto.split("\t")
    t = '<w:tab/>'.join(f'<w:t xml:space="preserve">{escape(p)}</w:t>' for p in partes)
    return f"<w:r>{rpr(**fmt)}{t}</w:r>"


def ppr(estilo=None, salto=False, keep=False, num=None, tabs=None,
        espacio=None, ind=None, jc="both", fuente=LORA, marca=None):
    """marca: formato de la marca de párrafo (Word lo aplica al número de lista)."""
    x = ""
    if estilo:
        x += f'<w:pStyle w:val="{estilo}"/>'
    if keep:
        x += '<w:keepNext w:val="1"/>'
    if salto:
        x += '<w:pageBreakBefore w:val="1"/>'
    if num:
        x += f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num}"/></w:numPr>'
    if tabs:
        x += f"<w:tabs>{tabs}</w:tabs>"
    if espacio:
        x += espacio
    if ind:
        x += ind
    if jc:
        x += f'<w:jc w:val="{jc}"/>'
    x += marca or rpr(fuente)
    return f"<w:pPr>{x}</w:pPr>"


class Memoria:
    def __init__(self, plantilla):
        self.doc = Document(str(plantilla))
        self.body = self.doc.element.body
        self.sect = self.body.find(qn("w:sectPr"))
        self.numeracion = self.doc.part.numbering_part.element
        self.tmp = Path(tempfile.mkdtemp(prefix="memoria_"))

    def xml(self, cadena):
        el = parse_xml(cadena)
        self.sect.addprevious(el)
        return el

    def p(self, runs="", **kw):
        return self.xml(f"<w:p {NS}>{ppr(**kw)}{runs}</w:p>")

    def vacio(self, fuente=LORA, b=False, sz=None):
        """Párrafo vacío: la referencia separa así los párrafos."""
        return self.xml(f'<w:p {NS}><w:pPr><w:jc w:val="both"/>'
                        f'{rpr(fuente, b=b, sz=sz)}</w:pPr></w:p>')

    def nueva_lista(self, abstracto):
        """Instancia nueva de una numeración de la plantilla (empieza en 1)."""
        ids = [int(n.get(qn("w:numId"))) for n in self.numeracion.findall(qn("w:num"))]
        nuevo = max(ids) + 1
        self.numeracion.append(parse_xml(
            f'<w:num {NS} w:numId="{nuevo}"><w:abstractNumId w:val="{abstracto}"/>'
            f'<w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride></w:num>'))
        return nuevo

    def enlace(self, url, texto, sz=None):
        rid = self.doc.part.relate_to(url, RT.HYPERLINK, is_external=True)
        return (f'<w:hyperlink r:id="{rid}">'
                f'{run(texto, color="1155cc", u=True, sz=sz)}</w:hyperlink>')

    def _ruta_imagen(self, ruta):
        ruta = resolver(ruta)
        if ruta.suffix.lower() == ".svg":
            raise SystemExit(f"Word no admite SVG: use un PNG ({ruta})")
        if ruta.suffix.lower() in (".webp", ".gif"):      # Word no admite WebP
            from PIL import Image
            png = self.tmp / (ruta.stem + ".png")
            Image.open(ruta).convert("RGB").save(png)
            ruta = png
        return str(ruta)

    def _centrar(self, par):
        sangria = '<w:ind w:left="0" w:firstLine="0"/>'
        pp = parse_xml(f'<w:p {NS}>{ppr(ind=sangria, jc="center")}</w:p>')[0]
        viejo = par._p.find(qn("w:pPr"))
        if viejo is not None:
            par._p.remove(viejo)
        par._p.insert(0, pp)

    def imagen(self, imagenes):
        """imagenes: [(ruta, fracción del ancho)]. Varias: en una fila, como
        tabla sin bordes (una celda por imagen)."""
        if len(imagenes) == 1:
            ruta, ancho = imagenes[0]
            par = self.doc.add_paragraph()               # se inserta antes de sectPr
            par.add_run().add_picture(self._ruta_imagen(ruta),
                                      width=Emu(int(ANCHO * 635 * ancho)))
            self._centrar(par)
        else:
            n = len(imagenes)
            tabla = self.doc.add_table(rows=1, cols=n)
            celda_w = ANCHO // n
            tbl = tabla._tbl
            sin = '<w:{} w:val="nil"/>'
            bordes = "".join(sin.format(b) for b in
                             ("top", "left", "bottom", "right", "insideH", "insideV"))
            tblpr = tbl.tblPr
            for hijo in list(tblpr):
                tblpr.remove(hijo)
            for x in (f'<w:tblW {NS} w:w="{ANCHO}" w:type="dxa"/>',
                      f'<w:jc {NS} w:val="center"/>',
                      f'<w:tblBorders {NS}>{bordes}</w:tblBorders>',
                      f'<w:tblLayout {NS} w:type="fixed"/>',
                      f'<w:tblCellMar {NS}><w:left w:w="40" w:type="dxa"/>'
                      f'<w:right w:w="40" w:type="dxa"/></w:tblCellMar>'):
                tblpr.append(parse_xml(x))
            for col in tbl.tblGrid.findall(qn("w:gridCol")):
                col.set(qn("w:w"), str(celda_w))
            for celda, (ruta, ancho) in zip(tabla.rows[0].cells, imagenes):
                celda.width = Emu(celda_w * 635)
                par = celda.paragraphs[0]
                ancho_max = (celda_w - 80) * 635
                par.add_run().add_picture(self._ruta_imagen(ruta),
                                          width=Emu(min(int(ANCHO * 635 * ancho), ancho_max)))
                self._centrar(par)
        self.vacio()

    def codigo(self, texto, titulo=None, sz=20):
        """Cuadro de una celda: título a la derecha y una línea por párrafo.
        sz: tamaño en medios puntos (20 = 10 pt, como en la referencia)."""
        f = dict(fuente=MONO, sz=sz)

        def pp(jc=""):
            return (f'<w:pPr><w:widowControl w:val="0"/>'
                    f'<w:spacing w:line="240" w:lineRule="auto"/>{jc}{rpr(**f)}</w:pPr>')
        filas = ""
        if titulo:
            derecha = '<w:jc w:val="right"/>'
            filas += f"<w:p>{pp(derecha)}{run(titulo, **f)}</w:p>"
        for linea in texto.expandtabs(4).split("\n"):
            filas += f"<w:p>{pp()}{run(linea, **f) if linea else ''}</w:p>"
        borde = '<w:{} w:color="000000" w:space="0" w:sz="8" w:val="single"/>'
        bordes = "".join(borde.format(b) for b in
                         ("top", "left", "bottom", "right", "insideH", "insideV"))
        self.xml(
            f'<w:tbl {NS}><w:tblPr><w:tblW w:w="{ANCHO}" w:type="dxa"/>'
            f'<w:jc w:val="left"/><w:tblBorders>{bordes}</w:tblBorders>'
            f'<w:tblLayout w:type="fixed"/><w:tblLook w:val="0600"/></w:tblPr>'
            f'<w:tblGrid><w:gridCol w:w="{ANCHO}"/></w:tblGrid><w:tr><w:tc>'
            f'<w:tcPr><w:tcW w:w="{ANCHO}" w:type="dxa"/><w:shd w:fill="auto" w:val="clear"/>'
            f'<w:tcMar><w:top w:w="100" w:type="dxa"/><w:left w:w="100" w:type="dxa"/>'
            f'<w:bottom w:w="100" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tcMar>'
            f'<w:vAlign w:val="top"/></w:tcPr>{filas}</w:tc></w:tr></w:tbl>')
        self.vacio()

    def tabla(self, cabecera, filas, anchos):
        borde = '<w:{} w:color="000000" w:space="0" w:sz="8" w:val="single"/>'
        bordes = "".join(borde.format(b) for b in
                         ("top", "left", "bottom", "right", "insideH", "insideV"))
        grid = "".join(f'<w:gridCol w:w="{a}"/>' for a in anchos)
        cuerpo = ""
        for n, fila in enumerate(([cabecera] if cabecera else []) + filas):
            negrita = cabecera is not None and n == 0
            celdas = ""
            for a, celda in zip(anchos, fila):
                pp = ppr(espacio='<w:spacing w:line="240" w:lineRule="auto"/>', jc="left")
                runs = self.inlines(celda, sz=20, b=negrita)
                celdas += (f'<w:tc><w:tcPr><w:tcW w:w="{a}" w:type="dxa"/>'
                           f'<w:tcMar><w:top w:w="60" w:type="dxa"/><w:left w:w="100" w:type="dxa"/>'
                           f'<w:bottom w:w="60" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tcMar>'
                           f'</w:tcPr><w:p>{pp}{runs}</w:p></w:tc>')
            cab = '<w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>' if negrita else '<w:trPr><w:cantSplit/></w:trPr>'
            cuerpo += f"<w:tr>{cab}{celdas}</w:tr>"
        self.xml(
            f'<w:tbl {NS}><w:tblPr><w:tblW w:w="{sum(anchos)}" w:type="dxa"/>'
            f'<w:jc w:val="left"/><w:tblBorders>{bordes}</w:tblBorders>'
            f'<w:tblLayout w:type="fixed"/><w:tblLook w:val="0600"/></w:tblPr>'
            f'<w:tblGrid>{grid}</w:tblGrid>{cuerpo}</w:tbl>')
        self.vacio()

    # --- texto en línea (AST de pandoc) -------------------------------------
    def inlines(self, lista, fuente=LORA, b=False, i=False, sz=None):
        out = ""
        for el in lista:
            t, c = el["t"], el.get("c")
            if t == "Str":
                out += run(c, fuente=fuente, b=b, i=i, sz=sz)
            elif t in ("Space", "SoftBreak"):
                out += run(" ", fuente=fuente, b=b, i=i, sz=sz)
            elif t == "LineBreak":
                out += "<w:r><w:br/></w:r>"
            elif t == "Strong":
                out += self.inlines(c, fuente, True, i, sz)
            elif t == "Emph":
                out += self.inlines(c, fuente, b, True, sz)
            elif t == "Code":
                out += run(c[1], fuente=MONO, b=b, i=i, sz=20 if sz is None else sz)
            elif t == "Link":
                texto = texto_plano(c[1])
                out += self.enlace(c[2][0], texto, sz=sz)
            elif t == "Quoted":
                out += run("“", fuente=fuente, b=b, i=i, sz=sz)
                out += self.inlines(c[1], fuente, b, i, sz)
                out += run("”", fuente=fuente, b=b, i=i, sz=sz)
            elif t in ("Span", "Underline", "SmallCaps", "Strikeout"):
                out += self.inlines(c[1] if t == "Span" else c, fuente, b, i, sz)
            elif t == "RawInline":
                pass
            else:
                raise SystemExit(f"Elemento en línea no previsto: {t}")
        return out

    # --- portada e índice ---------------------------------------------------
    def portada(self, meta):
        for _ in range(5):
            self.p(estilo="Title", fuente=LORA)
        self.p(run(meta["titulo"], fuente=MARC, b=True),
               estilo="Title", jc="center", fuente=MARC)
        self.p(jc="center", fuente=MARC)
        self.p(run(meta["subtitulo"], fuente=MARC, b=True),
               estilo="Subtitle", jc="center", fuente=MARC)
        if meta.get("subtitulo2"):
            self.p(run(meta["subtitulo2"], fuente=MARC),
                   estilo="Subtitle", jc="center", fuente=MARC)
        for _ in range(14):
            self.vacio(MARC, b=True, sz=24)
        self.p(run("Participantes:", fuente=MARC, b=True, sz=24), jc="right", fuente=MARC)
        for nombre in meta["participantes"]:
            self.p(run(nombre, fuente=MARC), jc="right", fuente=MARC)

    def indice(self, secciones, paginas):
        self.p(run("Índice", fuente=MARC, b=True, sz=24),
               estilo="Title", salto=True, fuente=MARC, marca=rpr(MARC, b=True, sz=24))
        lista = self.nueva_lista(3)
        tab = f'<w:tab w:val="right" w:leader="dot" w:pos="{ANCHO}"/>'
        for n, titulo in enumerate(secciones):
            pag = paginas[n] if paginas else "0"
            self.p(run(f"{titulo}\t{pag}"), num=lista, tabs=tab,
                   ind='<w:ind w:left="720" w:hanging="360"/>')


def resolver(ruta):
    """Rutas de imagen relativas a src/, a doc/ o a la raíz del repositorio."""
    for base in (SRC, SRC.parents[1], RAIZ):
        if (base / ruta).exists():
            return base / ruta
    raise SystemExit(f"No se encuentra la imagen {ruta}")


def texto_plano(inl):
    s = ""
    for el in inl:
        t, c = el["t"], el.get("c")
        if t == "Str":
            s += c
        elif t in ("Space", "SoftBreak"):
            s += " "
        elif t == "Code":
            s += c[1]
        elif t in ("Span", "Link", "Quoted"):
            s += texto_plano(c[1])
        elif t in ("Strong", "Emph", "Underline", "SmallCaps", "Strikeout"):
            s += texto_plano(c)
    return s


def meta_texto(v):
    if v["t"] in ("MetaInlines", "MetaString"):
        return texto_plano(v["c"]) if v["t"] == "MetaInlines" else v["c"]
    if v["t"] == "MetaList":
        return [meta_texto(x) for x in v["c"]]
    raise SystemExit(f"Metadato no previsto: {v['t']}")


# --------------------------------------------------------------------------
# Conversión
# --------------------------------------------------------------------------
def atributos(attr):
    return dict(attr[2])


def es_imagen(bloque):
    """Figura, o párrafo formado sólo por imágenes (varias = en la misma fila)."""
    if bloque["t"] == "Figure":
        return True
    return (bloque["t"] in ("Para", "Plain") and bloque["c"]
            and all(el["t"] in ("Image", "Space", "SoftBreak") for el in bloque["c"])
            and any(el["t"] == "Image" for el in bloque["c"]))


def imagenes_de(bloque):
    if bloque["t"] == "Figure":
        return [el for b in bloque["c"][2] for el in b["c"] if el["t"] == "Image"]
    return [el for el in bloque["c"] if el["t"] == "Image"]


def anchos_tabla(colspecs, filas):
    n = len(colspecs)
    rel = [c[1]["c"] if c[1]["t"] == "ColWidth" else None for c in colspecs]
    if all(rel):
        total = sum(rel)
        return [int(ANCHO * r / total) for r in rel]
    largos = [1] * n
    for fila in filas:
        for k, celda in enumerate(fila):
            largos[k] = max(largos[k], min(len(texto_plano(celda)), 60))
    total = sum(largos)
    return [int(ANCHO * l / total) for l in largos]


def celdas(fila):
    out = []
    for celda in fila[1]:
        bloques = celda[4]
        inl = []
        for b in bloques:
            if b["t"] in ("Plain", "Para"):
                if inl:
                    inl.append({"t": "LineBreak"})
                inl.extend(b["c"])
        out.append(inl)
    return out


def convertir(ast, paginas=None):
    m = Memoria(SRC / "plantilla_memoria.docx")
    meta = {k: meta_texto(v) for k, v in ast["meta"].items()}
    bloques = ast["blocks"]
    secciones = [texto_plano(b["c"][2]) for b in bloques
                 if b["t"] == "Header" and b["c"][0] == 1]
    m.portada(meta)
    m.indice(secciones, paginas)

    lista_apartados = lista_puntos = None
    for k, b in enumerate(bloques):
        t, c = b["t"], b.get("c")
        sig = bloques[k + 1] if k + 1 < len(bloques) else None
        if t == "Header":
            nivel, inl = c[0], c[2]
            if nivel == 1:
                m.p(m.inlines(inl, MARC, b=True, sz=24), estilo="Title", salto=True,
                    num=1, ind='<w:ind w:left="720" w:hanging="360"/>', fuente=MARC,
                    marca=rpr(MARC, b=True, sz=24))
                lista_apartados = m.nueva_lista(2)
                lista_puntos = None
            elif nivel == 2:
                m.p(m.inlines(inl), num=lista_apartados, keep=True,
                    ind='<w:ind w:left="720" w:hanging="360"/>')
                lista_puntos = None
            else:
                if lista_puntos is None:
                    lista_puntos = m.nueva_lista(4)
                m.p(m.inlines(inl, MARC), num=lista_puntos, keep=True,
                    ind='<w:ind w:left="720" w:hanging="360"/>', fuente=MARC)
        elif es_imagen(b):
            lista = []
            for img in imagenes_de(b):
                ancho = atributos(img["c"][0]).get("width", "100%")
                ancho = float(ancho.rstrip("%")) / 100 if ancho.endswith("%") else 1.0
                lista.append((img["c"][2][0], ancho))
            m.imagen(lista)
        elif t in ("Para", "Plain"):
            texto = texto_plano(c).rstrip()
            if re.match(r"\[\d+\] ", texto):          # referencia bibliográfica
                m.p(m.inlines(c), jc="left", ind='<w:ind w:left="0" w:firstLine="0"/>')
                m.vacio()
                continue
            m.p(m.inlines(c), keep=texto.endswith(":") and sig is not None
                and sig["t"] == "CodeBlock")
            # como en la referencia: «...:» va pegado al cuadro o imagen siguiente
            if not (texto.endswith(":") and sig and
                    (sig["t"] in ("CodeBlock", "Table") or es_imagen(sig))):
                m.vacio()
        elif t == "CodeBlock":
            attr = atributos(c[0])
            # los listados completos de los scripts (include) van a 7 pt
            m.codigo(c[1], attr.get("titulo"), 14 if "listado" in c[0][1] else 20)
        elif t == "BulletList":
            for item in c:
                for sub in item:
                    if sub["t"] in ("Plain", "Para"):
                        m.p(m.inlines(sub["c"]), ind='<w:ind w:firstLine="720"/>')
                    elif sub["t"] == "BulletList":
                        for it2 in sub["c"]:
                            for s2 in it2:
                                if s2["t"] in ("Plain", "Para"):
                                    m.p(m.inlines(s2["c"]),
                                        ind='<w:ind w:left="720" w:firstLine="720"/>')
            m.vacio()
        elif t == "OrderedList":
            lista = m.nueva_lista(2)
            for item in c[1]:
                for sub in item:
                    if sub["t"] in ("Plain", "Para"):
                        m.p(m.inlines(sub["c"]), num=lista,
                            ind='<w:ind w:left="720" w:hanging="360"/>')
            m.vacio()
        elif t == "Table":
            colspecs, head, cuerpos = c[2], c[3], c[4]
            cab = [celdas(f) for f in head[1]]
            filas = [celdas(f) for cuerpo in cuerpos for f in cuerpo[3]]
            m.tabla(cab[0] if cab else None, filas, anchos_tabla(colspecs, cab + filas))
        elif t in ("HorizontalRule", "RawBlock", "Div", "Null"):
            pass
        else:
            raise SystemExit(f"Bloque no previsto: {t}")
    return m


def pdf_de(docx, destino):
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise SystemExit("Falta LibreOffice (soffice) para generar el PDF")
    with tempfile.TemporaryDirectory() as perfil:
        subprocess.run([soffice, f"-env:UserInstallation=file://{perfil}", "--headless",
                        "--convert-to", "pdf", "--outdir", str(destino), str(docx)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return Path(destino) / (Path(docx).stem + ".pdf")


def paginas_secciones(pdf, secciones):
    """Página (numeración del pie: la portada no cuenta) de cada sección."""
    texto = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True,
                           capture_output=True, text=True).stdout.split("\f")
    paginas, desde = [], 2
    for n, titulo in enumerate(secciones, 1):
        patron = re.compile(rf"^\s*{n}\.\s*{re.escape(titulo[:30])}", re.M)
        for k in range(desde, len(texto)):
            primeras = "\n".join(l for l in texto[k].splitlines() if l.strip())[:300]
            if patron.search(primeras):
                paginas.append(str(k))           # k = índice 0 → pie = k
                desde = k + 1
                break
        else:
            raise SystemExit(f"No encuentro la sección «{titulo}» en el PDF")
    return paginas


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--md", default=str(SRC / "memoria.md"))
    ap.add_argument("--sin-pdf", action="store_true", help="sólo el .docx")
    args = ap.parse_args()

    ast = json.loads(subprocess.run(
        ["pandoc", args.md, "-t", "json", "--lua-filter", str(SRC / "include.lua")],
        check=True, capture_output=True, text=True, cwd=RAIZ).stdout)
    docx = SALIDA / "memoria.docx"
    m = convertir(ast)
    m.doc.save(docx)
    if args.sin_pdf:
        print(f"Generado {docx}")
        return
    secciones = [texto_plano(b["c"][2]) for b in ast["blocks"]
                 if b["t"] == "Header" and b["c"][0] == 1]
    with tempfile.TemporaryDirectory() as tmp:
        paginas = paginas_secciones(pdf_de(docx, tmp), secciones)
    m = convertir(ast, paginas)                  # índice con números de página
    m.doc.save(docx)
    pdf = pdf_de(docx, SALIDA)
    print(f"Generados {docx} y {pdf} (índice: {', '.join(paginas)})")


if __name__ == "__main__":
    main()
