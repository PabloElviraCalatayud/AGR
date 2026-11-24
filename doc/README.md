# Documentación

| Carpeta | Contenido |
|---|---|
| `entregables/` | PDF finales: **memoria completa (partes 1 y 2)**, `como_ejecutar.txt` (instrucciones breves), guía paso a paso, requisitos punto a punto, red del laboratorio, diagramas y manual de uso |
| `entregables/src/` | Fuentes Markdown de las memorias, estilos, imágenes e `include.lua` (inserta el código de los scripts en la memoria al generar el PDF) |
| `development/enunciado/` | Enunciado de la práctica y plan de numeración del laboratorio 3103 |
| `development/parte1/` | Medidas en bruto de la parte 1 (consumo de la VM) |
| `development/parte2/` | Capturas de pantalla, verificación de la red manual, informe de pruebas del script de despliegue y generador del diagrama de construcción |
| `development/historico_script/` | Primera versión automatizada de la parte 2 (sustituida por `parte2/`): su memoria, explicación, pruebas y XML |

Regenerar los PDF después de editar las fuentes:

```bash
doc/build_pdf.sh
```
