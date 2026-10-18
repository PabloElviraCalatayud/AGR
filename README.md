# AGR – Práctica 2: Virtualización

Administración y Gestión de Redes, curso 2026-2027. El repositorio es
autocontenido: incluye el enunciado, el plan de numeración, el código de las
dos partes y las memorias (fuentes y PDF).

```
.
├── parte1-vagrant/           Parte 1: servidor web Node.js en una VM con Vagrant
│   └── Vagrantfile
├── parte2-kvm/               Parte 2: red del laboratorio 3103 con QEMU-KVM
│   ├── agr_kvm.py            script de despliegue (Python + lxml)
│   ├── topologia.json        plan de numeración (redes, máquinas, rutas)
│   ├── plantilla_vm.xml      XML base de Moodle
│   └── guest/                ficheros que se instalan en las VMs
└── doc/
    ├── entregables/          PDF finales a entregar
    │   └── src/              fuentes Markdown de las memorias
    ├── development/          material de trabajo (enunciado, plano, medidas)
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
- **`VERR_VMX_IN_VMX_ROOT_MODE` / `VERR_SVM_IN_USE`:** KVM ocupa la
  virtualización. Ejecute `sudo modprobe -r kvm_intel kvm` (o `kvm_amd kvm`).

## Parte 2 – QEMU-KVM

Réplica del laboratorio 3103: 4 routers con FRR (RA–RD), servidor web
(10.100.0.11), un PC en cada una de las 4 redes inferiores, y el anfitrión
como PC del profesor (10.200.0.2).

```bash
sudo apt install qemu-system-x86 qemu-utils libvirt-daemon-system libvirt-clients \
                 libguestfs-tools dhcpcd-base python3-lxml xterm
cd parte2-kvm
sudo ./agr_kvm.py crear          # imagen base + bridges + 9 VMs
sudo ./agr_kvm.py probar         # plan de pruebas de conectividad
sudo ./agr_kvm.py consola rc     # consola de una VM (root / agr)
sudo ./agr_kvm.py destruir
```

KVM y VirtualBox no pueden usarse a la vez: apague la VM de la parte 1
(`vagrant halt`) y cargue KVM (`sudo modprobe kvm_amd` o `kvm_intel`).

Detalles en `doc/entregables/memoria_parte2.pdf`.

## Documentación

- `doc/entregables/memoria_parte1.pdf`: configuración, pruebas y estudio de
  consumo de la parte 1.
- `doc/entregables/memoria_parte2.pdf`: arquitectura, plan de numeración,
  tablas de enrutamiento y plan de pruebas de la parte 2.
- Para regenerar los PDF: `doc/build_pdf.sh` (requiere `pandoc` y
  Chromium/Chrome).
