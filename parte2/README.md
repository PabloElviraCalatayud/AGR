# Parte 2 — Red del laboratorio 3103 con QEMU-KVM

Réplica del laboratorio 3103 (`doc/development/enunciado/plan_numeracion_3103.pdf`)
montada a mano con KVM/libvirt: 4 routers con FRR (RA–RD), servidor web (SRV),
un PC por cada red inferior (PC1–PC4) y el anfitrión como PC Profesor.

La explicación completa, paso a paso, está en
`doc/entregables/guia_paso_a_paso.pdf`; las conexiones, rutas y pruebas en
`doc/entregables/red_laboratorio_3103.pdf`.

## Contenido

```
parte2/
├── plantilla.xml            XML de Moodle (base de todas las VMs)
├── xml/                     XML de cada VM = plantilla + nombre, disco y bridges
│   ├── molde.xml            VM temporal con Internet (red NAT "default")
│   ├── srv.xml  ra.xml  rb.xml  rc.xml  rd.xml
│   └── pc1.xml  pc2.xml  pc3.xml  pc4.xml
├── red.sh                   Prepara el anfitrión (tras cada reinicio)
├── molde/
│   ├── preparar_molde.sh    Órdenes ejecutadas dentro del molde (FRR, Node, servidor)
│   └── ssr-server.service   Servicio systemd del servidor web
└── vm/<vm>/                 Configuración de dentro de cada VM
    ├── hostname
    ├── interfaces           → /etc/network/interfaces
    ├── 99-router.conf       → /etc/sysctl.d/ (sólo routers: reenvío IP)
    └── frr.conf             → /etc/frr/frr.conf (sólo routers: rutas estáticas)
```

## Diseño

| Elemento | Decisión |
|---|---|
| Discos | Cadena qcow2: `base.qcow2` (Moodle, sólo lectura) ← `molde.qcow2` (software común, sólo lectura) ← un disco diferencial por VM, en `/var/lib/libvirt/images/lab3103/` |
| Redes | Un bridge Linux por red del plano: `br-srv`, `br-prof`, `br-ab`, `br-bc`, `br-bd`, `br-red1`…`br-red4` |
| Tarjetas | `eth0`, `eth1`, `eth2` en el orden de los `<interface>` del XML (la imagen arranca con `net.ifnames=0`) |
| IPs | Fijas, en `/etc/network/interfaces` (ifupdown) de cada VM |
| Routers | FRR 7.2.1 activo sólo en RA–RD, rutas estáticas del plano con `vtysh` |
| Servidor web | SSR-master-server (`node app.js`) activo sólo en SRV, puerto 3000 |
| Anfitrión | PC Profesor: 10.200.0.2/30 en `br-prof`, rutas al laboratorio vía RA |

| VM | Tarjetas (bridge → IP) | Puerta de enlace / rutas |
|---|---|---|
| SRV | eth0 br-srv 10.100.0.11/24 | gw 10.100.0.1 |
| RA | eth0 br-srv 10.100.0.1/24 · eth1 br-ab 10.1.0.1/30 · eth2 br-prof 10.200.0.1/30 | 0/0 → 10.1.0.2 |
| RB | eth0 br-ab 10.1.0.2/30 · eth1 br-bc 10.2.0.1/30 · eth2 br-bd 10.3.0.1/30 | 10.0.1–2.0/24 → 10.2.0.2; 10.0.3–4.0/24 → 10.3.0.2; 0/0 → 10.1.0.1 |
| RC | eth0 br-bc 10.2.0.2/30 · eth1 br-red1 10.0.1.1/24 · eth2 br-red2 10.0.2.1/24 | 0/0 → 10.2.0.1 |
| RD | eth0 br-bd 10.3.0.2/30 · eth1 br-red3 10.0.3.1/24 · eth2 br-red4 10.0.4.1/24 | 0/0 → 10.3.0.1 |
| PC1–PC4 | eth0 br-redN 10.0.N.10/24 | gw 10.0.N.1 |

## Uso

Tras cada reinicio del anfitrión:

```bash
./red.sh
for vm in srv ra rb rc rd pc1 pc2 pc3 pc4; do sudo virsh start $vm; done
sudo virsh list --all
sudo virsh console ra            # root / agr ; salir con Ctrl+]
```

Crear una VM desde cero (ejemplo, PC1):

```bash
cd /var/lib/libvirt/images/lab3103
sudo qemu-img create -f qcow2 -F qcow2 -b molde.qcow2 pc1.qcow2
sudo virsh define ~/AGR/parte2/xml/pc1.xml
sudo virsh start pc1
# dentro: hostnamectl set-hostname pc1 ; copiar vm/pc1/interfaces a
#         /etc/network/interfaces ; systemctl restart networking
```

Cambiar el XML de una VM que ya existe: `virsh shutdown` → esperar a
`shut off` → `virsh undefine` → `virsh define` → `virsh start`.

## Estado

Verificado el 10/11/2026: las 9 VMs llegan a las 18 IPs del laboratorio y al
servidor web (`doc/development/parte2/verificacion_final.txt`).

**Pendiente:** el script que automatice el despliegue completo (lo pide el
enunciado: «desarrollar un script que despliegue una red virtualizada» que
«deberá generar los ficheros XML»).
