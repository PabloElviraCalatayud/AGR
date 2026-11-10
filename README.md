# AGR – Práctica 2: Virtualización

Administración y Gestión de Redes, curso 2026-2027. El repositorio es
autocontenido: incluye el enunciado, el plan de numeración, el código de las
dos partes y las memorias (fuentes y PDF).

```
.
├── parte1-vagrant/           Parte 1: servidor web Node.js en una VM con Vagrant
│   └── Vagrantfile
├── parte2/                  Parte 2: red del laboratorio 3103 con QEMU-KVM
│   ├── plantilla.xml         XML base de Moodle
│   ├── xml/                  XML de las 9 VMs (y del molde)
│   ├── red.sh                prepara el anfitrión: KVM, bridges, IP de PC Profesor
│   ├── molde/                preparación de la imagen común (FRR, Node, servidor)
│   └── vm/<vm>/              configuración de dentro de cada VM
└── doc/
    ├── entregables/          PDF finales a entregar
    │   └── src/              fuentes Markdown de las memorias
    ├── development/          material de trabajo (enunciado, plano, medidas,
    │                         capturas, histórico de la primera versión con script)
    └── build_pdf.sh          regenera los PDF
```

## Parte 1 – Vagrant + VirtualBox

VM Ubuntu 22.04 con Node.js y
[SSR-master-server](https://github.com/gisai/SSR-master-server) como servicio
systemd, accesible en el puerto **3000** de la VM y **8080** del anfitrión.

| Elemento | Valor |
|---|---|
| Box | `bento/ubuntu-22.04` (clon enlazado) |
| Recursos | 1 CPU (tope 80 %), 1024 MB RAM (`VM_CPUS`, `VM_MEMORY`) |
| NIC 1 | NAT + port forwarding `host:8080 → guest:3000` |
| NIC 2 / NIC 3 | host-only `192.168.56.10` (servicio) y `192.168.57.10` (gestión) |
| NIC 4 (opcional) | bridge por DHCP: `BRIDGE_IF=<interfaz> vagrant up` |
| Sistema | teclado `es`, `es_ES.UTF-8`, `Europe/Madrid`, `ufw` (22 y 3000) |
| Login | se imprime la configuración del servidor |

```bash
cd parte1-vagrant
vagrant up
vagrant ssh
curl http://localhost:8080
```

### Instalación de VirtualBox y Vagrant (Ubuntu)

```bash
# VirtualBox (repositorio de Oracle)
wget -O- https://www.virtualbox.org/download/oracle_vbox_2016.asc \
  | sudo gpg --dearmor --yes -o /usr/share/keyrings/oracle-virtualbox-2016.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/oracle-virtualbox-2016.gpg] https://download.virtualbox.org/virtualbox/debian $(lsb_release -cs) contrib" \
  | sudo tee /etc/apt/sources.list.d/virtualbox.list
sudo apt update && sudo apt install -y virtualbox-7.2 build-essential dkms linux-headers-$(uname -r)
sudo usermod -aG vboxusers $USER

# Vagrant (repositorio de HashiCorp)
wget -O- https://apt.releases.hashicorp.com/gpg \
  | sudo gpg --dearmor --yes -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install -y vagrant
```

Problemas habituales:

- **Secure Boot activo:** `modprobe vboxdrv` falla. Desactívelo en la BIOS
  (o registre la clave MOK) y ejecute `sudo /sbin/vboxconfig`.
- **`VERR_VMX_IN_VMX_ROOT_MODE` / `VERR_SVM_IN_USE`:** hay VMs de KVM
  encendidas; apáguelas (`sudo virsh shutdown <vm>`). El `Vagrantfile`
  descarga KVM y carga VirtualBox antes de arrancar.

## Parte 2 – QEMU-KVM

Réplica del laboratorio 3103 montada a mano con KVM/libvirt a partir de la
imagen y el XML de Moodle: 4 routers con FRR (RA–RD), servidor web SRV
(10.100.0.11:3000), un PC en cada una de las 4 redes inferiores (PC1–PC4) y el
anfitrión como PC Profesor (10.200.0.2). Detalles en `parte2/README.md`.

```bash
cd parte2
./red.sh                                   # tras cada reinicio del anfitrión
for vm in srv ra rb rc rd pc1 pc2 pc3 pc4; do sudo virsh start $vm; done
sudo virsh console ra                      # root / agr ; salir con Ctrl+]
```

Verificado: las 9 VMs llegan a las 18 IPs del laboratorio y al servidor web.

KVM y VirtualBox no pueden usarse a la vez: apague las VMs de la otra parte
(`vagrant halt` o `sudo virsh shutdown <vm>`); `red.sh` y el `Vagrantfile`
cargan y descargan los módulos.

**Pendiente:** el script que automatice el despliegue de `parte2/`.

## Documentación

Todo en `doc/entregables/` (PDF) con sus fuentes Markdown en `doc/entregables/src/`:

| Documento | Contenido |
|---|---|
| `guia_paso_a_paso` | **La práctica completa paso a paso**: cada orden, qué hace, qué debe salir y los problemas encontrados |
| `requisitos_punto_a_punto` | **Cada requisito del enunciado**: cita, qué pide, cómo se ha implementado, dónde está, cómo se comprueba y estado |
| `red_laboratorio_3103` | Memoria de la red de la parte 2: diagrama, plan de numeración, tablas de rutas, tabla de accesos, plan de pruebas, consumo e incidencias |
| `diagrama_red_lab3103` (PDF/PNG) | Diagrama de red: equipos, bridges, tarjetas, puertos del plano e IPs |
| `diagrama_construccion_lab3103` (PDF/PNG) | El mismo diagrama con la orden con que se creó cada enlace y cada equipo |
| `memoria_parte1` | Parte 1: configuración, pruebas y estudio de consumo |
| `manual_usuario` | Manual de uso de las dos partes |

Para regenerar los PDF: `doc/build_pdf.sh` (requiere `pandoc` y Chromium/Chrome).
