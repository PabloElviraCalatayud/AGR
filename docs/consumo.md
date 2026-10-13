# Estudio de consumo del servicio virtualizado

Medidas tomadas sobre la VM `agr-nodeserver` desplegada con el `Vagrantfile`
(Ubuntu 22.04, 1 vCPU, 1 GB RAM, Node.js 22 + SSR-master-server). Los datos en
bruto están en [`consumo_raw.txt`](consumo_raw.txt).

**Anfitrión:** AMD Ryzen 7 7700X (8 núcleos / 16 hilos), 30 GiB RAM,
Ubuntu 24.04, VirtualBox 7.2.20, Vagrant 2.4.9.

**Metodología:** medidas desde el anfitrión (`ps`, `VBoxManage metrics`, `du`)
y desde el invitado (`free`, `df`, `top`), en reposo y durante una carga de
5000 peticiones HTTP secuenciales a `/record` a través del port forwarding
(`localhost:8080 → VM:3000`). Antes se habían enviado ~20 000 peticiones.
El crecimiento de la imagen se vigiló con
`watch "ls -al ~/VirtualBox\ VMs/agr-nodeserver/Snapshots/"`.

## 1. Memoria

| Medida | Reposo | Con carga | Tras carga |
|---|---|---|---|
| RSS del proceso `VBoxHeadless` (anfitrión) | **1.04 GiB** | 1.05 GiB | 1.05 GiB |
| RAM usada por el invitado (sin caché) | 202 MiB | 206 MiB | 204 MiB |
| Caché de disco del invitado | 685 MiB | 680 MiB | 692 MiB |
| RSS del proceso `node app.js` | 85 MiB | 86 MiB | — |

- La aplicación es ligera: el SO + servidor solo usan **~200 MiB**, y Node ~85 MiB.
- Sin embargo, al anfitrión **la VM le cuesta toda la RAM asignada (1 GB) más
  ~70 MiB de sobrecarga de VirtualBox**: el invitado usa la memoria libre como
  caché de disco y VirtualBox no la devuelve. En virtualización completa se
  paga la RAM *reservada*, no la *necesaria*.
- La carga apenas mueve la memoria (+10 MiB): el servidor no acumula estado.
- Conclusión: podría asignarse **512 MiB** sin pérdida de servicio y reducir
  el coste a la mitad.

## 2. CPU

| Medida | Reposo | Con carga |
|---|---|---|
| CPU del anfitrión usada por la VM | ~0.06 % | **~2.3 %** (≈ 0.37 hilos de 16) |
| CPU del invitado (user + kernel) | 0 % | ~24 % de 1 vCPU |
| `node` en `top` | 0.5 % | 26.7 % |

- En reposo la VM es prácticamente gratuita en CPU.
- Con carga se sirvieron **5000 peticiones en 40.9 s (~122 pet/s, ~8 ms por
  petición)**. El cuello de botella no es el servidor (vCPU al 24 %) sino el
  cliente: un `curl` nuevo por petición, en serie. Con clientes concurrentes
  la VM admitiría bastante más tráfico antes de saturar su vCPU.
- Parte del coste es de kernel (≈ 1/3), debido a la red virtual NAT y a la
  escritura en disco de cada petición.

## 3. Disco

| Elemento | Tamaño |
|---|---|
| Box base `bento/ubuntu-22.04` (`~/.vagrant.d/boxes`) | 811 MiB |
| Disco diferencial de la VM (clon enlazado, `Snapshots/*.vmdk`) | **2.1 GiB** |
| Uso dentro del invitado | 5.5 GiB de 31 GiB virtuales |
| Logs CSV tras ~25 000 registros | 1.2 MiB (53 ficheros) |

- Gracias a `linked_clone` la VM no copia la imagen base: solo guarda las
  diferencias (paquetes, Node.js, `node_modules`, logs). Una segunda VM igual
  costaría otros ~2 GiB, no 5.5.
- El disco es *dinámico*: los 31 GiB son un máximo, el fichero crece al
  escribirse bloques nuevos. Durante la carga de 5000 peticiones el `.vmdk`
  no cambió de forma visible (2.1G): los datos generados (~0.4 MiB, ≈ 50–80 B
  por registro) son despreciables frente a la granularidad de bloques del
  disco virtual. Al ritmo medido harían falta ~1 M de registros para crecer
  ~50–80 MiB.
- Si los datos se borran dentro de la VM el `.vmdk` **no** encoge; habría que
  compactarlo (`VBoxManage modifymedium --compact`).

## 4. Estimación: red virtualizada del laboratorio 3103

> El número de máquinas debe ajustarse al dibujo de Moodle. Se supone aquí una
> red de **8 VMs**: 3 routers, 1 servidor web y 4 PCs (uno por subred).

Coste por VM tomado de las medidas: **~1.07 GiB RAM** en el anfitrión con 1 GB
asignado, ~0.06 % CPU en reposo, ~2 GiB de disco diferencial (+ 811 MiB de
base compartida).

| Escenario | RAM anfitrión | Disco | CPU en reposo |
|---|---|---|---|
| 8 VMs como esta (1 GB cada una) | ~8.6 GiB | ~17 GiB (clones) / ~44 GiB (copias completas) | < 1 % |
| Optimizado: routers y PCs a 256 MiB, servidor a 512 MiB | ~2.6 GiB | ~10 GiB | < 1 % |

- En el anfitrión usado (30 GiB) la red completa cabe con holgura: la red sin
  optimizar ocupa ~29 % de la RAM; el límite práctico serían ~25 VMs de 1 GB.
- **La RAM es el recurso limitante**, no la CPU: una VM de router/PC está
  ociosa casi siempre.
- Con KVM (segunda parte) el coste baja: imágenes `qcow2` con *backing file*
  (equivalente a los clones enlazados), y KSM (*Kernel Same-page Merging*)
  permite que VMs con el mismo SO compartan páginas de memoria idénticas.

## 5. Comparación con servidores comerciales

Un servidor de rack actual de 2 sockets (p. ej. AMD EPYC 9005 o Intel Xeon 6)
ofrece del orden de **hasta 384 núcleos / 768 hilos y 1–6 TB de RAM**.

Con las cifras medidas, para un servidor de 1 TB de RAM y 768 hilos:

| Límite | Cálculo | VMs como esta |
|---|---|---|
| RAM (dejando ~10 % al hipervisor) | 920 GiB / 1.07 GiB | **~860** |
| CPU con carga como la del ensayo | 768 hilos / 0.37 hilos | ~2000 |
| CPU en reposo | — | prácticamente ilimitado |

- De nuevo, la RAM manda: ese servidor alojaría **~100 redes de laboratorio
  completas** (8 VMs) sin optimizar, o ~350 con la configuración optimizada.
- Frente al anfitrión de prácticas (16 hilos, 30 GiB), el servidor comercial
  tiene ~48× hilos y ~33× RAM.
- Para un servicio así de ligero (85 MiB de Node) una VM completa
  desperdicia memoria: con **contenedores** (Docker/LXC), que comparten el
  kernel del anfitrión, cada instancia costaría ~100 MiB en lugar de ~1 GiB,
  es decir, ~10× más densidad. Las VMs compensan cuando se necesita
  aislamiento fuerte o un kernel/SO distinto (p. ej. routers con su propia
  pila de red, como en la segunda parte).

## 6. Conclusiones

1. El servidor Node.js necesita ~200 MiB de RAM y muy poca CPU; la VM en
   cambio consume toda la RAM asignada en el anfitrión.
2. El dimensionado importa: bajar a 512 MiB reduce el coste a la mitad sin
   afectar al servicio.
3. Los clones enlazados y los discos dinámicos reducen mucho el disco
   ocupado; los datos de la aplicación son despreciables.
4. Para replicar redes completas, la RAM es el cuello de botella; la CPU sólo
   importa con carga real.
