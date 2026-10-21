# Imagen de las máquinas virtuales

Coloque aquí la imagen de disco de Moodle con el nombre **`agr-vm-base.qcow2`**
(Ubuntu 20.04, usuario `root`, contraseña `agr`). `agr_kvm.py crear` la usa
como punto de partida de todas las VMs; nunca la modifica (trabaja sobre una
copia en `/var/lib/libvirt/images/agr/`).

La imagen (~2 GB) no se guarda en git: GitHub rechaza ficheros de más de
100 MB. Si no está aquí, el script la descarga del Release `imagen-moodle` del
repositorio:

    https://github.com/PabloElviraCalatayud/AGR/releases/download/imagen-moodle/agr-vm-base.qcow2
