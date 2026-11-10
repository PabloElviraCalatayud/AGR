# Histórico: primera versión automatizada de la parte 2 (script `agr_kvm.py`)

Antes de montar la red a mano se desarrolló un script, `parte2-kvm/agr_kvm.py`,
que desplegaba el laboratorio con otro diseño (bridges `agr-*`, VMs `agr-*`,
interfaces renombradas `ge0-0-x` por MAC, servicio `agr-net` y una imagen base
construida con `virt-customize`). Se sustituyó por la versión manual de
`parte2/`, que es la que se entrega y documenta.

El código del script sigue en el historial de git (último commit que lo
contiene: el anterior a la eliminación de `parte2-kvm/`). Aquí se conservan los
documentos y datos que lo describían, como material de trabajo:

| Fichero | Contenido |
|---|---|
| `memoria_parte2.pdf` (+ `src/`) | Memoria de la parte 2 escrita para el script |
| `explicacion_tecnica.pdf` (+ `src/`) | Explicación técnica del script y sus ficheros |
| `creacion_maquinas_virtuales.pdf` (+ `src/`) | Creación de las VMs con Vagrant (parte 1) y con el script |
| `pruebas_script.txt` | Informe de `agr_kvm.py probar` (50/50) |
| `consumo_kvm_script.txt` | RAM de las 9 VMs del script (384/768 MB): 3.6 GiB |
| `xml_generados/` | XML y configuraciones generados por el script |
