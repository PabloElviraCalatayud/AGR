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
├── despliegue.py            Script de despliegue automático (Python + lxml)
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

## Despliegue automático: `despliegue.py`

El script hace, sin intervención, lo mismo que los pasos 0–12 de la guía:

| Orden | Qué hace |
|---|---|
| `sudo ./despliegue.py instalar` | Instala las dependencias del anfitrión (QEMU/KVM, libvirt, libguestfs, lxml, xterm…) |
| `sudo ./despliegue.py molde` | Construye `molde.qcow2` sobre `base.qcow2` ejecutando `molde/preparar_molde.sh` dentro de la imagen con `virt-customize` (sólo si no existe; `--rehacer` para repetirlo) |
| `sudo ./despliegue.py crear [vms]` | Prepara el anfitrión (KVM, 9 bridges, IP de PC Profesor y rutas), y por cada VM: disco diferencial sobre el molde, configuración de `vm/<vm>/` escrita dentro del disco, XML generado con `lxml` desde `plantilla.xml`, `virsh define` y `virsh start`. Espera a que todas estén listas |
| `sudo ./despliegue.py probar [--informe f]` | Plan de pruebas: anfitrión → 17 IPs, web y `/record`; `traceroute` a cada PC; desde cada VM (por SSH) ping a las 18 IPs y web; tablas de rutas de los routers |
| `sudo ./despliegue.py estado` | Estado de cada VM con sus tarjetas, bridges e IPs |
| `sudo ./despliegue.py consola ra rb` | Un `xterm` con `virsh console` por VM, en segundo plano |
| `sudo ./despliegue.py parar` / `arrancar` | `virsh shutdown` de todas / preparar el anfitrión y `virsh start` |
| `sudo ./despliegue.py destruir [vms]` | `virsh destroy` + `undefine`, borra sus discos y, sin argumentos, bridges y rutas. Conserva `base.qcow2` y `molde.qcow2` |
| `./despliegue.py xml` | Sólo genera los XML en `xml/` (no necesita root) |
| `sudo ./despliegue.py consumo` | RAM real de cada VM (RSS de su proceso QEMU), memoria disponible en el anfitrión y disco ocupado |

**Laboratorio completo.** Con la opción global `--completo` se despliegan los
38 equipos del plano: los 4 routers, SRV1 (`srv`, 10.100.0.11), SRV2 (`srv2`,
10.100.0.21) y 8 PC por red (`pcN` con la .10 y `pcN-2` … `pcN-8` con la .11 …
.17). Su `/etc/network/interfaces` se genera a partir del plan. Por ejemplo,
con 512 MB y 1 CPU por VM:

```bash
sudo ./despliegue.py --completo crear --ram 512 --cpus 1 --espera 1800
sudo ./despliegue.py --completo consumo
sudo ./despliegue.py --completo probar --informe /tmp/pruebas38.txt
sudo ./despliegue.py destruir      # borra también los equipos del laboratorio completo
```

Opciones: `-v` (trazas de depuración con `logging`), `crear --ram MB` y
`--cpus N` (RAM y CPUs por VM; por defecto, las de la plantilla: 1 GB y 2 CPUs),
`molde --proxy URL`.

Antes del primer uso hay que copiar la imagen de Moodle como
`/var/lib/libvirt/images/lab3103/base.qcow2`. El script inyecta en cada VM una
clave SSH propia (`/var/lib/libvirt/images/lab3103/clave_lab`) para las pruebas.

Desplegar desde cero:

```bash
sudo ./despliegue.py instalar          # una vez
sudo ./despliegue.py destruir          # si ya había VMs
sudo ./despliegue.py crear
sudo ./despliegue.py probar --informe /tmp/pruebas.txt
```

## Uso manual (sin el script)

Tras cada reinicio del anfitrión:

```bash
./red.sh
for vm in srv ra rb rc rd pc1 pc2 pc3 pc4; do sudo virsh start $vm; done
sudo virsh list --all
sudo virsh console ra            # root / agr ; salir con Ctrl+]
```

Cambiar el XML de una VM que ya existe: `virsh shutdown` → esperar a
`shut off` → `virsh undefine` → `virsh define` → `virsh start`.

## Estado

Verificado el 10/11/2026: las 9 VMs llegan a las 18 IPs del laboratorio y al
servidor web (`doc/development/parte2/verificacion_final.txt`).

El despliegue automático con `despliegue.py` se comprueba con
`sudo ./despliegue.py probar`.
