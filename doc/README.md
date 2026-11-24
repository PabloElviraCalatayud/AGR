# Documentación

| Carpeta | Contenido |
|---|---|
| `entregables/` | PDF finales: **memoria completa (partes 1 y 2)** en Word y PDF, con el formato de la memoria de referencia, `como_ejecutar.txt` (instrucciones breves), guía paso a paso, requisitos punto a punto, red del laboratorio, diagramas y manual de uso |
| `entregables/src/` | Fuentes Markdown, estilos e imágenes. `memoria_docx.py` genera la memoria en Word a partir de `memoria.md` y `plantilla_memoria.docx` (estilos, fuentes y numeraciones de la memoria de referencia); `include.lua` inserta el código de los scripts |
| `development/enunciado/` | Enunciado de la práctica y plan de numeración del laboratorio 3103 |
| `development/parte1/` | Medidas en bruto de la parte 1 (consumo de la VM) |
| `development/parte2/` | Capturas de pantalla, verificación de la red manual, informe de pruebas del script de despliegue y generador del diagrama de construcción |
| `development/historico_script/` | Primera versión automatizada de la parte 2 (sustituida por `parte2/`): su memoria, explicación, pruebas y XML |

Regenerar los PDF después de editar las fuentes:

```bash
doc/build_pdf.sh
```
