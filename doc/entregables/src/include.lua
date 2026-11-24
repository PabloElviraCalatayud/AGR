-- include.lua - Inserta el contenido de un fichero del repositorio en un
-- bloque de código:   ```{.python include="parte2/despliegue.py"}
--                      ```
-- Las rutas son relativas a la raíz del repositorio (build_pdf.sh ejecuta
-- pandoc desde allí), así la memoria muestra siempre el código entregado.
function CodeBlock(el)
  local ruta = el.attributes.include
  if ruta == nil then
    return nil
  end
  local f = io.open(ruta, "r")
  if f == nil then
    io.stderr:write("include.lua: no se encuentra " .. ruta .. "\n")
    os.exit(1)
  end
  el.text = f:read("a"):gsub("\n$", "")
  f:close()
  el.attributes.include = nil
  if el.attributes.titulo == nil then          -- título del cuadro (memoria_docx.py)
    el.attributes.titulo = ruta:match("[^/]+$")
  end
  table.insert(el.classes, "listado")   -- estilo de listado largo (estilo.css)
  return el
end
