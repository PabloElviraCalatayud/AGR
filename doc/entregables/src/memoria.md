---
titulo: "Administración y Gestión de Redes"
subtitulo: "Virtualización de servicios web con Vagrant y de infraestructura de red con KVM"
subtitulo2: "Práctica 2"
participantes:
  - "Pablo, Elvira Calatayud"
---

# Configuración previa

Vagrant es una aplicación libre que usa el lenguaje Ruby para facilitar la
creación y personalización de entornos virtuales de desarrollo. Vagrant nos
abstrae del sistema de virtualización subyacente y nos permite instalar y
configurar el software de la máquina virtual, de modo que las mismas máquinas
pueden ejecutarse con distintos gestores de máquinas virtuales, como VirtualBox
o VMware [1][2].

Para empezar, hemos tenido que instalar el entorno de Vagrant, que
utilizaremos sobre VirtualBox [4]. Todo el trabajo se ha hecho en nuestro
propio equipo: un AMD Ryzen 7 7700X de 8 núcleos y 16 hilos, con 30 GiB de RAM
y Ubuntu 24.04. Hemos instalado VirtualBox y Vagrant desde los repositorios
oficiales de Oracle y de HashiCorp con los siguientes comandos:

```
wget -O- https://www.virtualbox.org/download/oracle_vbox_2016.asc \
  | sudo gpg --dearmor --yes -o /usr/share/keyrings/oracle-virtualbox-2016.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/oracle-virtualbox-2016.gpg] https://download.virtualbox.org/virtualbox/debian $(lsb_release -cs) contrib" \
  | sudo tee /etc/apt/sources.list.d/virtualbox.list
sudo apt update && sudo apt install -y virtualbox-7.2 build-essential dkms linux-headers-$(uname -r)
sudo usermod -aG vboxusers $USER

wget -O- https://apt.releases.hashicorp.com/gpg \
  | sudo gpg --dearmor --yes -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install -y vagrant
```

Podemos comprobar si se ha instalado correctamente consultando las versiones
con los siguientes comandos en la terminal:

```
vagrant -v
VBoxManage --version
```

En nuestro caso, Vagrant 2.4.9 y VirtualBox 7.2.20.

Antes de que VirtualBox funcionara tuvimos que resolver varios problemas del
equipo anfitrión. Vagrant respondía `No usable default provider` porque el
módulo del kernel de VirtualBox (`vboxdrv`) no se cargaba. Por un lado, el
kernel era demasiado nuevo para VirtualBox 7.1, así que actualizamos a la
versión 7.2. Por otro, el arranque seguro (Secure Boot) rechazaba el módulo,
firmado con una clave no registrada, así que lo desactivamos en la BIOS y
ejecutamos `sudo /sbin/vboxconfig`. Por último, los errores `VERR_SVM_IN_USE`
aparecían porque KVM ocupaba la virtualización del procesador. VirtualBox y KVM
no pueden usarla a la vez, por lo que hay que descargar los módulos de KVM
antes de arrancar las máquinas de Vagrant. Nuestro `Vagrantfile` lo hace
automáticamente.

En esta práctica vamos a editar el `Vagrantfile`, que contiene el tipo de
máquina virtual y su configuración para que se adapte a lo pedido. En Vagrant
se usan “boxes”, que son las imágenes base a partir de las cuales se crean las
máquinas virtuales. El `Vagrantfile` se puede compartir para replicar el mismo
entorno en otros equipos, lo que proporciona portabilidad.

Para la segunda parte usaremos QEMU-KVM. KVM es el hipervisor integrado en el
kernel de Linux, QEMU emula el resto del hardware de la máquina virtual, y
libvirt permite definir las máquinas mediante ficheros XML y gestionarlas con
el comando `virsh` [8][9]. Todas las dependencias del anfitrión las instala
nuestro script de la segunda parte con el siguiente comando:

```
sudo ./despliegue.py instalar
```

Este comando instala `qemu-system-x86`, `qemu-utils`, `libvirt-daemon-system`,
`libvirt-clients`, `libguestfs-tools`, `python3-lxml`, `bridge-utils`, `xterm`,
`traceroute` y otras utilidades.

Como base de las máquinas virtuales hemos descargado la imagen de disco
«maestro» y el fichero XML proporcionados en el Moodle. La imagen es un
Ubuntu 20.04 LTS cuyo superusuario es `root`, con la contraseña `agr`. La hemos
copiado sin modificarla como `/var/lib/libvirt/images/lab3103/base.qcow2`, y el
XML lo hemos guardado como `parte2/plantilla.xml`.

Todo el código y la documentación están en un repositorio Git
(<https://github.com/PabloElviraCalatayud/AGR>). La carpeta `parte1-vagrant`
contiene el `Vagrantfile`. La carpeta `parte2` contiene el script de
despliegue con KVM y sus ficheros. En `doc` están esta memoria, el enunciado,
el plano del laboratorio, las medidas y las capturas.

# Script de Vagrant en Ruby

En este apartado se nos ha pedido crear un script Vagrant (en lenguaje Ruby)
para desplegar una máquina virtual Linux en la que se ejecute un servidor web
Node.js. Como servidor hemos usado SSR-master-server
(<https://github.com/gisai/SSR-master-server>) [5].

El servidor debe ser accesible por el puerto exterior 8080 y por el puerto 3000
en la propia máquina virtual. El script debe instalar Node.js, descargar el
código del servidor de GitHub y ejecutarlo.

Además, hemos querido que la máquina virtual tenga el teclado en español y que,
al iniciar sesión en ella, se imprima la configuración del servidor.

```{.ruby include="parte1-vagrant/Vagrantfile"}
```

El script desarrollado implementa una infraestructura que despliega un
servidor web Node.js sobre una máquina virtual Linux. A continuación se
detallan sus bloques funcionales:

## Virtualización y sistema base

Imagen (box): se utiliza `bento/ubuntu-22.04` (Ubuntu 22.04 LTS). Hemos
elegido una versión LTS (Long Term Support) para garantizar el soporte y la
compatibilidad con Node.js 22.

Se han asignado 1024 MB de RAM y 1 CPU, que pueden cambiarse con las variables
de entorno `VM_MEMORY` y `VM_CPUS`. Además, con `--cpuexecutioncap 80` la
máquina no puede usar más del 80 % de una CPU del anfitrión. Después, con el
estudio de consumo, veremos si estos recursos son suficientes.

La máquina se crea como clon enlazado (`linked_clone`): no copia la imagen
base, sino que sólo guarda sus diferencias, lo que ahorra espacio en disco y
acelera la creación. Se llama `agr-nodeserver`, tanto en VirtualBox como en su
hostname.

## Arquitectura de red avanzada (multihoming)

Para simular un entorno de producción realista, hemos configurado la máquina
virtual como un equipo *multi-homed*: un dispositivo conectado a varias redes
mediante múltiples interfaces y direcciones IP, para lograr mayor fiabilidad y
separar el tráfico [3]. En nuestro caso, la máquina tiene hasta cuatro
interfaces de red, igual que un servidor real con una red de servicio, otra de
gestión y salida a Internet:

- Interfaz NAT: permite que la máquina tenga acceso a Internet para descargar paquetes y repositorios.
- Redirección de puertos: se mapea el puerto 3000 de la máquina virtual al puerto 8080 del anfitrión, en todas sus interfaces. Así el servidor web es accesible desde el navegador del anfitrión e incluso desde otros equipos de la red local.
- Red privada de servicio (192.168.56.10): una interfaz host-only que permite acceder al servidor web directamente en `http://192.168.56.10:3000`.
- Red privada de gestión (192.168.57.10): una segunda interfaz host-only, separada de la del servicio, para administrar la máquina.
- Red pública (opcional): una interfaz en modo puente (bridge) sobre una interfaz física del anfitrión, con IP por DHCP de la red local. Se activa con `BRIDGE_IF=<interfaz> vagrant up`.

## Aprovisionamiento idempotente (scripts de shell)

La sección de aprovisionamiento automatiza la instalación del software
necesario. La hemos dividido en cuatro scripts de shell, diseñados siguiendo
principios de idempotencia: pueden ejecutarse varias veces (`vagrant
provision`) sin generar errores ni duplicidades. Todos empiezan con `set -euo
pipefail`, de modo que si un paso falla el aprovisionamiento se detiene.

- Sistema: configura el teclado español en la consola y en el entorno gráfico (`/etc/default/keyboard`, `setupcon`, `localectl`, `loadkeys es`), el idioma `es_ES.UTF-8` y la zona horaria `Europe/Madrid`. Instala los paquetes base y activa el cortafuegos `ufw`, que deniega todo el tráfico entrante salvo SSH (22/tcp) y el servidor web (3000/tcp).
- Node: instala Node.js 22 desde el repositorio oficial de NodeSource [6], sólo si no está ya instalada esa versión.
- Servidor: crea el usuario sin privilegios `nodeapp`. Si el proyecto no existe, realiza un `git clone` en `/opt/ssr-master-server`; si ya existe, un `git pull` para actualizarlo. Después instala las dependencias con `npm install`.
- Información al iniciar sesión: desactiva el mensaje de bienvenida de Ubuntu e instala el script que imprime la configuración del servidor.

## Gestión del servicio mediante systemd

Para ejecutar el servidor hemos descartado `nohup`, por considerarlo poco
robusto. En su lugar hemos creado una unidad de servicio systemd
(`ssr-server.service`) [7]. Esto garantiza:

- Persistencia: mediante `systemctl enable`, el servidor web arranca automáticamente tras cualquier reinicio de la máquina virtual.
- Resiliencia: la directiva `Restart=on-failure` hace que, si el proceso de Node.js se detiene por un error, el sistema lo vuelva a levantar automáticamente.
- Seguridad: el servidor se ejecuta con el usuario `nodeapp`, sin privilegios de administrador.
- Operatividad: el servidor se gestiona con los comandos estándar de Linux (`systemctl start/stop/status/restart ssr-server`).

Hay que señalar que el servidor no se arranca con `npm start`: el fichero
`app.js` ya pone el servidor a escuchar en el puerto 3000, y `bin/www`, que es
lo que ejecuta `npm start`, vuelve a escuchar en el mismo puerto, por lo que
falla con el error `EADDRINUSE`. Por eso el servicio ejecuta directamente
`node app.js`.

## Configuración del servidor al iniciar sesión

El script `/etc/profile.d/99-servidor-info.sh` se ejecuta cada vez que
iniciamos sesión en la máquina (`vagrant ssh`) e imprime su configuración: el
sistema (hostname, versión de Ubuntu, kernel, CPUs, memoria, disco, teclado y
zona horaria), la red (direcciones IP de cada interfaz, puerta de enlace y
DNS), el estado del servicio web (activo o detenido), las versiones de Node.js
y npm, las direcciones desde las que se accede al servidor, los puertos en
escucha y las reglas del cortafuegos.

## Preparación del anfitrión

Como VirtualBox y KVM no pueden usar a la vez la virtualización del
procesador, antes de arrancar la máquina el script descarga los módulos de KVM
si están cargados, y carga el de VirtualBox. Así la máquina arranca aunque
antes se haya usado la segunda parte de la práctica.

Finalmente, para lanzar nuestra máquina virtual y comprobar su funcionamiento,
debemos introducir los siguientes comandos en la terminal, en el directorio
donde está el `Vagrantfile`:

```
cd parte1-vagrant
vagrant up
vagrant ssh
```

Al terminar `vagrant up`, Vagrant muestra cómo acceder al servidor:

```
VM agr-nodeserver lista.
  - Desde el anfitrión:   http://localhost:8080
  - Por la red privada:   http://192.168.56.10:3000
  - Dentro de la VM:      http://localhost:3000
Entre con "vagrant ssh" para ver la configuración del servidor.
```

Con la máquina ya iniciada, podemos acceder a la página web del servidor
introduciendo `http://localhost:8080` en el navegador del anfitrión. Desde
dentro de la máquina responde en `http://localhost:3000`, y por la red privada
en `http://192.168.56.10:3000`. También hemos comprobado que el servidor guarda
los datos que recibe, con una petición como la siguiente, que crea un fichero
CSV en la carpeta `/logs` del servidor:

```
curl "http://localhost:8080/record?id_nodo=n1&temperatura=24.5&humedad=60&co2=300&volatiles=100"
```

# Estudio del consumo de memoria

Para valorar la eficiencia del entorno virtualizado, hemos realizado
mediciones en tiempo real tanto en el sistema anfitrión como dentro de la
máquina virtual. Nuestra máquina tiene 1024 MB (1 GB) de RAM, 1 núcleo de CPU,
y como sistema operativo `bento/ubuntu-22.04`.

Hemos medido en reposo y durante una carga de 5000 peticiones HTTP seguidas a
`/record` a través de la redirección de puertos (antes ya se habían enviado
unas 20 000). En el anfitrión hemos usado `ps` para el proceso de la máquina
virtual y `VBoxManage metrics`. Dentro de la máquina, `free`, `df`, `top` y
`ps`. Además, como propone el enunciado, hemos vigilado con `watch` cómo crecía
la imagen de la máquina:

```
watch "ls -al ~/VirtualBox\ VMs/agr-nodeserver/Snapshots/"
```

Estas son las medidas obtenidas, tal y como las guardamos en el fichero
`consumo_raw.txt` del repositorio:

```{titulo="consumo_raw.txt" include="doc/development/parte1/consumo_raw.txt"}
```

### Consumo de memoria (RAM)

Dentro de la máquina virtual, el sistema operativo junto con el servidor
Node.js consumen apenas 202 MB de memoria RAM, sin contar la caché de disco.
Como hemos asignado 1024 MB a la máquina, sólo estamos usando alrededor del
20 % de los recursos disponibles. El proceso `node app.js` ocupa unos 85 MB.
Durante la carga, la memoria apenas aumenta (unos 4 MB), porque el servidor no
acumula estado.

Sin embargo, al anfitrión la máquina le cuesta toda la RAM asignada: el
proceso de VirtualBox ocupa 1.04 GiB, es decir, el gigabyte asignado más unos
70 MB de sobrecarga. La máquina usa la memoria libre como caché de disco
(685 MB) y VirtualBox no la devuelve al anfitrión. En la virtualización
completa se paga la memoria reservada, no la necesaria.

Esto demuestra que podríamos reducir la asignación a 512 MB sin afectar al
rendimiento, lo que reduciría el coste a la mitad, o desplegar varias réplicas
de este servidor en el mismo equipo físico sin saturarlo.

### Consumo de CPU

El consumo de CPU en reposo es prácticamente nulo: un 0.06 % de la CPU del
anfitrión, con una carga media de 0.04 dentro de la máquina. Esto indica que
la sobrecarga de la virtualización para este tipo de servicio web es
despreciable.

Durante la carga, la máquina sirvió las 5000 peticiones en 40.9 segundos
(unas 122 peticiones por segundo, unos 8 ms por petición). La CPU virtual
estuvo al 24 % y el proceso `node` al 26.7 %, mientras que el anfitrión sólo
dedicó a la máquina un 2.3 % de su CPU. El límite no lo puso el servidor, sino
el cliente, que lanzaba un `curl` tras otro. Con clientes en paralelo, la
máquina admitiría bastante más tráfico. Alrededor de un tercio del tiempo de
CPU es del kernel, por la red virtual NAT y por la escritura en disco de cada
petición.

### Almacenamiento y crecimiento de la imagen

La imagen base de Ubuntu (`~/.vagrant.d/boxes`) ocupa 811 MB y se almacena una
única vez en el disco del equipo físico. Gracias al clon enlazado, la máquina
virtual sólo guarda sus diferencias respecto a ella (los paquetes, Node.js, las
dependencias del servidor y los registros): 2.1 GB, aunque dentro de la
máquina se usan 5.5 GB de un disco virtual de 31 GB.

El disco virtual es dinámico: los 31 GB son un máximo, y el fichero sólo crece
cuando se escriben bloques nuevos. Durante la carga de 5000 peticiones, `watch`
mostró que el fichero de la imagen no crecía de forma apreciable (seguía en
2.1 GB). Los datos generados (unos 0.4 MB, entre 50 y 80 bytes por registro)
son despreciables frente al tamaño de los bloques del disco virtual. Al ritmo
medido, harían falta alrededor de un millón de registros para que la imagen
creciera entre 50 y 80 MB. Si los datos se borran dentro de la máquina, la
imagen no encoge: habría que compactarla con `VBoxManage modifymedium
--compact`.

### Consumo de una red que replique el laboratorio

Según el plano del laboratorio 3103, el laboratorio tiene 4 routers, 2
servidores, el PC del profesor y 4 redes de 8 PC. Replicarlo entero supondría
38 máquinas virtuales (el PC del profesor sería el propio anfitrión). La
réplica reducida que permite el enunciado, con un único PC por red, son 9
máquinas.

Con las medidas anteriores, cada máquina cuesta unos 1.07 GB de RAM en el
anfitrión, un 0.06 % de CPU en reposo y unos 2 GB de disco, más la imagen base
compartida. Si se ajustara la RAM (256 MB para routers y PC y 512 MB para los
servidores), cada router o PC costaría unos 0.32 GB y cada servidor unos
0.57 GB:

| Escenario | Máquinas | RAM del anfitrión | Disco | CPU en reposo |
|---|---|---|---|---|
| Laboratorio completo, 1 GB por máquina | 38 | 41 GB | 77 GB | 2 % |
| Laboratorio completo, RAM ajustada | 38 | 12.7 GB | 40 GB | 2 % |
| Réplica reducida, 1 GB por máquina | 9 | 9.6 GB | 19 GB | menos del 1 % |
| Réplica reducida, RAM ajustada | 9 | 3.1 GB | 10 GB | menos del 1 % |

El laboratorio completo sin ajustar no cabría en nuestro equipo (30 GB de
RAM). Con la RAM ajustada ocuparía el 42 %, y la réplica reducida cabe de
sobra. El recurso que limita es la memoria, no la CPU, porque un router o un PC
del laboratorio está casi siempre ocioso. En el disco, al compartir la imagen
base, cada máquina sólo ocupa sus diferencias. En la segunda parte lo hemos
comprobado con KVM: las 9 máquinas ocupan 6.1 GB de RAM y unos 140 MB de disco
cada una. Además, KVM puede compartir entre máquinas las páginas de memoria
idénticas (KSM) [18].

### Comparación con los servidores comerciales

Un servidor de rack actual de dos procesadores, como los AMD EPYC serie 9005 o
los Intel Xeon 6 [16][17], alcanza 384 núcleos (768 hilos) y varios terabytes
de RAM. En un servidor así, con 1 TB de RAM y reservando un 10 % para el
hipervisor, cabrían unas 860 máquinas como la nuestra (920 GB / 1.07 GB). Por
CPU, con una carga como la de nuestra prueba, cabrían unas 2000 (768 hilos /
0.37 hilos). De nuevo, el límite lo pone la memoria.

Ese servidor podría alojar unas 22 réplicas completas del laboratorio, o unas
70 con la RAM ajustada. Frente a nuestro equipo (16 hilos y 30 GB), tiene unas
48 veces más hilos y unas 33 veces más memoria.

Para un servicio tan ligero como el nuestro, una máquina virtual completa
desperdicia memoria. Con contenedores (Docker o LXC), que comparten el kernel
del anfitrión, cada instancia costaría unos 100 MB en lugar de 1 GB: unas diez
veces más densidad. Las máquinas virtuales compensan cuando se necesita un
aislamiento fuerte o un sistema propio, como los routers de la segunda parte,
que tienen su propia pila de red.

# Virtualización de infraestructura de red con KVM

Se nos ha pedido desarrollar el script que despliegue la siguiente red
empleando la tecnología QEMU-KVM:

![](img/red_enunciado.png){width="80%"}

El script debe generar los ficheros XML de todas las máquinas virtuales,
instalar la Software Routing Suite en los routers y configurar las rutas
estáticas necesarias para lograr la conectividad global. En el servidor debe
desplegar un servicio web, para el que hemos reutilizado el de la primera
parte. El objetivo final es que cualquier máquina de las redes inferiores, y
también el anfitrión, tenga acceso al servicio web del servidor.

## Plan de numeración

Para la numeración hemos seguido el plano del laboratorio 3103 publicado en el
Moodle, que da las direcciones de cada red, los puertos de los routers y sus
tablas de enrutamiento:

![](img/plan_numeracion_3103.png){width="85%"}

El enunciado permite que cada una de las cuatro redes inferiores sea un único
PC, así que nuestra red tiene 9 máquinas virtuales:

- Los 4 routers del plano (RA, RB, RC y RD), con FRR como Software Routing Suite.
- El servidor web (SRV), con la dirección 10.100.0.11, que es la de las máquinas virtuales de SRV1 en el plano.
- Un PC en cada red inferior (PC1, PC2, PC3 y PC4), con la dirección .10 de su red.

El anfitrión hace de PC del profesor, con la dirección 10.200.0.2 en su enlace
con RA. En cada red, el router tiene la dirección .1. Las redes de PC son /24,
y los enlaces entre routers y el del PC del profesor son /30.

Cada red del plano es un *bridge* de Linux en el anfitrión, que hace de
switch. Cada tarjeta de red de una máquina virtual es un tap que libvirt
conecta a su bridge al arrancar la máquina. Dentro de las máquinas, las
tarjetas se llaman `eth0`, `eth1` y `eth2`, en el orden en que aparecen en su
XML. El dibujo de nuestra red es el siguiente:

![](entregables/diagrama_red_lab3103.png)

| Equipo | Tarjeta (puerto del plano) | Bridge | Dirección IP | Puerta de enlace |
|---|---|---|---|---|
| RA | eth0 (ge0/0/3) · eth1 (ge0/0/1) · eth2 (ge0/0/5) | br-srv · br-ab · br-prof | 10.100.0.1/24 · 10.1.0.1/30 · 10.200.0.1/30 | — |
| RB | eth0 (ge0/0/5) · eth1 (ge0/0/1) · eth2 (ge0/0/4) | br-ab · br-bc · br-bd | 10.1.0.2/30 · 10.2.0.1/30 · 10.3.0.1/30 | — |
| RC | eth0 (ge0/0/5) · eth1 (ge0/0/1) · eth2 (ge0/0/2) | br-bc · br-red1 · br-red2 | 10.2.0.2/30 · 10.0.1.1/24 · 10.0.2.1/24 | — |
| RD | eth0 (ge0/0/5) · eth1 (ge0/0/3) · eth2 (ge0/0/4) | br-bd · br-red3 · br-red4 | 10.3.0.2/30 · 10.0.3.1/24 · 10.0.4.1/24 | — |
| SRV | eth0 | br-srv | 10.100.0.11/24 | 10.100.0.1 (RA) |
| PC1 | eth0 | br-red1 | 10.0.1.10/24 | 10.0.1.1 (RC) |
| PC2 | eth0 | br-red2 | 10.0.2.10/24 | 10.0.2.1 (RC) |
| PC3 | eth0 | br-red3 | 10.0.3.10/24 | 10.0.3.1 (RD) |
| PC4 | eth0 | br-red4 | 10.0.4.10/24 | 10.0.4.1 (RD) |
| Anfitrión (PC Profesor) | br-prof | br-prof | 10.200.0.2/30 | 10.200.0.1 (RA) para las 8 redes del laboratorio |

## Tablas de enrutamiento

Los routers de los extremos (RA, RC y RD) sólo necesitan una ruta por defecto
hacia RB, porque todo lo que no está directamente conectado a ellos está
detrás de RB. RB es el único que necesita conocer el detalle: las redes de PC
de cada rama y una ruta por defecto hacia RA, que lleva a la red de servidores
y al PC del profesor. En total bastan 8 rutas estáticas, las mismas del plano:

| Router | Destino | Siguiente salto |
|---|---|---|
| RA | 0.0.0.0/0 | 10.1.0.2 (RB) |
| RB | 10.0.1.0/24 y 10.0.2.0/24 | 10.2.0.2 (RC) |
| RB | 10.0.3.0/24 y 10.0.4.0/24 | 10.3.0.2 (RD) |
| RB | 0.0.0.0/0 | 10.1.0.1 (RA) |
| RC | 0.0.0.0/0 | 10.2.0.1 (RB) |
| RD | 0.0.0.0/0 | 10.3.0.1 (RB) |

Las rutas se configuran en FRR [13][14] con el comando `ip route <destino>
<siguiente salto>` en `vtysh`, y se guardan con `write memory` en el fichero
`/etc/frr/frr.conf` de cada router. Las tablas que muestra cada router con
`show ip route` aparecen en las capturas del apartado 5.

## Script de despliegue

Para este apartado hemos escrito el script `despliegue.py` en Python, usando
la librería lxml para los ficheros XML, como recomienda el enunciado. El
script se apoya en la plantilla XML de Moodle (`plantilla.xml`), en la carpeta
`molde`, con el software común a todas las máquinas, y en la carpeta `vm`, con
la configuración de cada máquina:

```{.python include="parte2/despliegue.py"}
```

A continuación se detallan los bloques funcionales del script:

### Plan de numeración en el script

Al principio del script, el plan de numeración se declara una sola vez, en dos
diccionarios: `REDES` contiene cada bridge con su red, y `VMS` cada máquina
con su papel (router, servidor o PC), los bridges de sus tarjetas en orden
(`eth0`, `eth1`, `eth2`) y sus direcciones IP. Todo lo demás se obtiene de
ellos: los bridges, los XML, las rutas del anfitrión y las direcciones que se
comprueban en las pruebas.

### Preparación del anfitrión

La función `preparar_anfitrion` descarga los módulos de VirtualBox si están
cargados y carga los de KVM (`kvm_amd` o `kvm_intel`, según el procesador).
Después arranca libvirt y crea los 9 bridges. También desactiva el filtrado
del cortafuegos sobre los bridges, para que no bloquee el tráfico entre
máquinas. Por último, da al anfitrión la dirección del PC del profesor
(10.200.0.2) y una ruta a cada red del laboratorio a través de RA.

### Generación de los XML con lxml

La función `generar_xml` lee con lxml [10] la plantilla de Moodle y modifica
sólo lo necesario. Cambia el nombre (`<name>`) y la ruta del disco
(`<source file=...>`). Si se pide otra cantidad de RAM, cambia también la
memoria. Por último, sustituye la única tarjeta de red de la plantilla por una
tarjeta por cada bridge de la máquina, en orden. Así, en RA quedan tres
tarjetas, conectadas a `br-srv`, `br-ab` y `br-prof`, que dentro de la máquina
serán `eth0`, `eth1` y `eth2`.

### Molde con el software común

Todas las máquinas necesitan el mismo software, así que, para no instalarlo
nueve veces, el script crea un disco «molde». Con `qemu-img` [11] crea un disco
diferencial sobre la imagen de Moodle, que nunca se modifica. Después, con
`virt-customize` [12], ejecuta dentro de él, sin arrancar la máquina, el script
`preparar_molde.sh`:

```{.bash include="parte2/molde/preparar_molde.sh"}
```

Este script instala FRR (desactivado, porque sólo se activa en los routers),
herramientas de red, el servidor SSH, Node.js 22 y el servidor web
SSR-master-server, igual que en la primera parte. El servidor queda como
servicio de systemd, aunque sin activar, porque sólo se activa en SRV:

```{include="parte2/molde/ssr-server.service"}
```

### Disco y configuración de cada máquina

Cada máquina tiene su propio disco diferencial sobre el molde, que sólo ocupa
unos 140 MB. Antes de arrancarla, el script escribe con `virt-customize` su
configuración dentro del disco:

- su nombre (hostname);
- sus direcciones IP, en `/etc/network/interfaces`;
- la clave SSH del anfitrión, para las pruebas, y unas claves de servidor SSH propias.

En los routers escribe además la activación del reenvío IP y la configuración
de FRR con sus rutas estáticas, y activa FRR. En el servidor activa el
servicio web. De este modo, las máquinas arrancan ya configuradas y no hay que
entrar en ellas para configurarlas. Los ficheros de cada máquina se muestran en
el apartado 5.

### Gestión de las máquinas con virsh y xterm

Siguiendo las recomendaciones del enunciado, todas las máquinas se gestionan
con `virsh` (`define`, `start`, `shutdown`, `destroy` y `undefine`). La orden
`consola` abre una terminal `xterm` con la consola de cada máquina
(`xterm -e "virsh console <máquina>"`) en segundo plano, para que el script no
se quede detenido.

### Mensajes con print y trazas con logging

Los mensajes que el programa siempre muestra se imprimen con `print`, con el
prefijo `>>>`. Para depurar el script usamos el módulo `logging` de Python
[15]: los mensajes de progreso salen siempre, y con la opción `-v` se muestra
además cada comando que se ejecuta. Así, las trazas de depuración se eliminan
sin tocar el código, simplemente quitando `-v`.

## Despliegue de la red

Después hemos introducido los siguientes comandos en la terminal para preparar
el anfitrión, construir el molde y desplegar toda la red:

```
git clone -b claude/peaceful-lovelace-6f6vcz https://github.com/PabloElviraCalatayud/AGR.git
cd AGR/parte2
sudo ./despliegue.py instalar
sudo ./despliegue.py molde
sudo ./despliegue.py crear
```

El comando `crear` crea los 9 bridges y las 9 máquinas virtuales con sus
tarjetas y direcciones, espera a que todas estén listas y muestra su estado
final:

![](development/parte2/capturas/despliegue_crear.png)

Para entrar en cualquiera de las máquinas, con el usuario `root` y la
contraseña `agr`, usamos el siguiente comando:

```
sudo ./despliegue.py consola ra
```

## Configuración de cada máquina

Antes de escribir el script, configuramos y comprobamos la red a mano, máquina
a máquina. El script aplica exactamente la misma configuración, con los mismos
ficheros. En cada máquina se muestran sus interfaces (`ip -br a`) y sus rutas
(`ip route`). En los routers se muestra también la tabla de FRR
(`show ip route`), y en el servidor el puerto 3000 en escucha. Al final de cada
captura aparece el resultado de hacer ping a las 18 direcciones de la red y de
pedir la página web al servidor.

Direcciones IP del router RA:

```{titulo="vm/ra/interfaces" include="parte2/vm/ra/interfaces"}
```

Rutas estáticas de RA:

```{titulo="vm/ra/frr.conf" include="parte2/vm/ra/frr.conf"}
```

![](development/parte2/capturas/verificacion_ra.webp)

Direcciones IP del router RB:

```{titulo="vm/rb/interfaces" include="parte2/vm/rb/interfaces"}
```

Rutas estáticas de RB:

```{titulo="vm/rb/frr.conf" include="parte2/vm/rb/frr.conf"}
```

![](development/parte2/capturas/verificacion_rb.webp)

Direcciones IP del router RC:

```{titulo="vm/rc/interfaces" include="parte2/vm/rc/interfaces"}
```

Rutas estáticas de RC:

```{titulo="vm/rc/frr.conf" include="parte2/vm/rc/frr.conf"}
```

![](development/parte2/capturas/verificacion_rc.webp)

Direcciones IP del router RD:

```{titulo="vm/rd/interfaces" include="parte2/vm/rd/interfaces"}
```

Rutas estáticas de RD:

```{titulo="vm/rd/frr.conf" include="parte2/vm/rd/frr.conf"}
```

![](development/parte2/capturas/verificacion_rd.webp)

En los cuatro routers el reenvío IP se activa con el mismo fichero:

```{titulo="vm/ra/99-router.conf" include="parte2/vm/ra/99-router.conf"}
```

Direcciones IP del servidor:

```{titulo="vm/srv/interfaces" include="parte2/vm/srv/interfaces"}
```

![](development/parte2/capturas/verificacion_srv.webp)

Direcciones IP del PC1:

```{titulo="vm/pc1/interfaces" include="parte2/vm/pc1/interfaces"}
```

![](development/parte2/capturas/verificacion_pc1.webp)

Direcciones IP del PC2:

```{titulo="vm/pc2/interfaces" include="parte2/vm/pc2/interfaces"}
```

![](development/parte2/capturas/verificacion_pc2.webp)

Direcciones IP del PC3:

```{titulo="vm/pc3/interfaces" include="parte2/vm/pc3/interfaces"}
```

![](development/parte2/capturas/verificacion_pc3.webp)

Direcciones IP del PC4:

```{titulo="vm/pc4/interfaces" include="parte2/vm/pc4/interfaces"}
```

![](development/parte2/capturas/verificacion_pc4.webp)

## Plan de pruebas

Para confirmar que existe conectividad global, hemos comprobado tres cosas:
que cualquier equipo llega a cualquier otro, que todos acceden al servicio web
y que el tráfico sigue el camino previsto por las tablas de enrutamiento.

Durante la construcción manual fuimos probando cada paso antes de seguir con el
siguiente. Primero comprobamos el ping entre RA y el servidor. Después, el
enlace entre RA y RB: antes de configurar las rutas, RB no llegaba al servidor
(*Network is unreachable*), como era de esperar, y con las rutas ya llegaba. A
continuación probamos las ramas de RC y RD con ping y `traceroute`, los PC y el
anfitrión, y por último el servicio web desde PC1, PC4 y el anfitrión.

Para la prueba final, el script incluye la orden `probar`, que comprueba toda
la red en cuatro bloques:

- Desde el anfitrión: ping a las 17 direcciones de las máquinas virtuales, petición de la página web (debe devolver el código 200) y petición a `/record` (escritura de datos).
- Desde el anfitrión: `traceroute` a cada PC, cuyo último salto debe ser el propio PC.
- Desde cada una de las 9 máquinas, por SSH: ping a las 18 direcciones de la red (todas las tarjetas y el anfitrión) y petición de la página web.
- En cada router: la tabla de FRR debe contener las rutas estáticas instaladas (`S>*`).

En cada máquina se ejecuta, en concreto, la siguiente comprobación:

```
ok=0; fail=''
for ip in 10.100.0.11 10.100.0.1 10.1.0.1 10.200.0.1 10.1.0.2 10.2.0.1 10.3.0.1 \
          10.2.0.2 10.0.1.1 10.0.2.1 10.3.0.2 10.0.3.1 10.0.4.1 \
          10.0.1.10 10.0.2.10 10.0.3.10 10.0.4.10 10.200.0.2; do
  if ping -c1 -W1 $ip >/dev/null 2>&1; then ok=$((ok+1)); else fail="$fail $ip"; fi
done
web=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://10.100.0.11:3000/)
echo "$ok $web$fail"
```

Con la red desplegada por el script hemos lanzado el plan de pruebas con el
siguiente comando:

```
sudo ./despliegue.py probar --informe /tmp/pruebas.txt
```

El resultado son 36 pruebas correctas de 36. Todos los pings responden, todas
las máquinas acceden al servidor web y los routers tienen sus rutas
instaladas:

![](development/parte2/capturas/despliegue_probar.png)

Por último, desde el anfitrión hemos mostrado el estado de las máquinas, hemos
hecho un `traceroute` a PC4 y una petición al servidor web, y hemos consultado
el informe completo de las pruebas, que incluye el camino hasta cada PC y la
tabla de cada router:

```
sudo ./despliegue.py estado
traceroute -n 10.0.4.10
curl -s -o /dev/null -w "%{http_code}\n" http://10.100.0.11:3000/
cat /tmp/pruebas.txt
```

![](development/parte2/capturas/despliegue_estado_informe.png)

El `traceroute` desde el anfitrión hasta PC4 pasa por RA (10.200.0.1), RB
(10.1.0.2) y RD (10.3.0.2) antes de llegar a PC4 (10.0.4.10), y el de PC1
pasa por RA, RB y RC. Es justo el camino que marcan las tablas de enrutamiento.
Desde los PC hacia el servidor, el camino es el inverso: el router de su red,
RB y RA. El número de routers atravesados se confirma también con el TTL de
las respuestas: 64 si el destino está en la misma red, 63 si hay un router de
por medio y 61 si hay tres.

## Consumo de la red virtualizada

Con las 9 máquinas en marcha, cada una con la RAM de la plantilla de Moodle
(1 GB y 2 CPU), la memoria real que ocupa cada máquina en el anfitrión es de
unos 690 MB (760 MB el servidor, por el proceso de Node.js). En total, 6.1 GB:
un 20 % de la RAM de nuestro equipo. KVM sólo reserva la memoria que la
máquina usa realmente, por eso cada una ocupa menos del gigabyte asignado, al
contrario que con VirtualBox.

En disco, la imagen de Moodle ocupa 2.0 GB, el molde 1.2 GB y cada máquina
entre 136 y 146 MB, unos 4.5 GB en total. Copiar la imagen completa para cada
máquina costaría unos 29 GB. Ambas cifras son menores que las que habíamos
estimado en el estudio de consumo para la réplica reducida (9.6 GB de RAM y
19 GB de disco). Si se quisiera reducir más la memoria, el script permite
asignar menos RAM a todas las máquinas con `crear --ram`.

## Configuraciones adicionales

Además de lo mínimo que pide el enunciado, hemos añadido las siguientes
configuraciones:

- En las máquinas virtuales: cada una tiene su propio nombre, el servidor web es un servicio de systemd con un usuario sin privilegios, todas tienen acceso por SSH con la clave del anfitrión y herramientas de diagnóstico (`traceroute`, `tcpdump`, `curl`), y cada `/etc/network/interfaces` indica en comentarios la red y el puerto del plano de cada tarjeta.
- En FRR: cada router tiene su nombre (RA, RB, RC y RD), sólo se activan los servicios necesarios (`zebra` y `staticd`), y la configuración se guarda con `write memory`. Además, hemos hecho las rutas más robustas: si el router va cargado, el vigilante de FRR (`watchfrr`) puede reiniciar `staticd` por separado y perder las rutas. Para evitarlo, la configuración se vuelve a aplicar cada vez que FRR arranca, y los tiempos de `watchfrr` son más tolerantes.
- En el script: el plan de pruebas automático con informe, las órdenes para parar, arrancar, destruir y consultar el estado de la red, la convivencia con VirtualBox y la posibilidad de funcionar en equipos sin KVM, con emulación.

## Incidencias

Durante la construcción manual de la red tuvimos estos problemas:

- Después de reiniciar la red de RB (`systemctl restart networking`), RC no llegaba al servidor: el reinicio había borrado la ruta por defecto que FRR había instalado, y FRR no la volvió a poner. Se soluciona reiniciando FRR (`systemctl restart frr`) después de reiniciar la red.
- PC3 no llegaba a su puerta de enlace (*Destination Host Unreachable*) porque todavía no habíamos creado RD.
- Tras reiniciar el anfitrión, las máquinas no arrancaban (*Cannot get interface MTU*) porque los bridges no se conservan. El script los vuelve a crear con `despliegue.py arrancar`.
- `virsh define` fallaba con *domain already exists* al volver a definir una máquina. El script hace siempre `undefine` antes de `define`.
- Al editar un XML a mano quedaron dos tarjetas de red repetidas. Por eso el script genera los XML con lxml a partir de la plantilla.
- `virsh list` sin `sudo` no mostraba ninguna máquina, porque se conecta a otra instancia de libvirt (`qemu:///session`). El script usa siempre `qemu:///system`.

Al automatizar el despliegue aparecieron otros:

- Las máquinas arrancaban sin servidor SSH, porque la imagen base no trae las claves del servidor SSH (normalmente las genera cloud-init en el primer arranque). El script genera unas claves propias en cada disco antes de arrancar la máquina.
- Al construir el molde sin acceso al repositorio de NodeSource se instalaba el Node.js 10 de Ubuntu, que no incluye `npm`. Ahora, si NodeSource no está disponible, se instala Node.js desde su web oficial, y cualquier error detiene la construcción.
- Dentro de `virt-customize` no se encontraba el comando `node`, porque se ejecuta con un PATH mínimo. Se soluciona indicando el PATH en el script del molde.
- El comando `crear` se detenía si un router tardaba en responder por SSH. Ahora lo trata como «todavía no está listo» y vuelve a intentarlo.

## Conclusiones

La red del laboratorio 3103 se despliega con QEMU-KVM con un solo comando
(`crear`), a partir de la imagen y el XML de Moodle, y se comprueba con otro
(`probar`): 36 pruebas correctas de 36. Todos los equipos se alcanzan entre sí
y acceden al servicio web.

Gracias a un diseño jerárquico bastan 8 rutas estáticas: rutas por defecto en
los routers de los extremos y el detalle sólo en RB. Construir primero la red a
mano nos permitió entender cada pieza (bridges, taps, XML y FRR) y detectar los
problemas que luego el script resuelve de forma sistemática. Por último, KVM
con discos diferenciales resulta mucho más eficiente que la estimación hecha
con VirtualBox: 6.1 GB de RAM y 4.5 GB de disco para las 9 máquinas.

# Anexo

[1] HashiCorp, "Vagrant Documentation". [En línea]. Disponible: https://developer.hashicorp.com/vagrant/docs

[2] R. Ruiz, "Entornos virtuales de desarrollo con Vagrant", Raulr.net. [En línea]. Disponible: https://www.raulr.net/Entornos-virtuales-desarrollo-Vagrant/

[3] F5, "What Is Multi-Homing?", F5. [En línea]. Disponible: https://www.f5.com/glossary/multi-homing

[4] Oracle, "Oracle VirtualBox User Guide". [En línea]. Disponible: https://www.virtualbox.org/manual/

[5] GISAI, "SSR-master-server", GitHub. [En línea]. Disponible: https://github.com/gisai/SSR-master-server

[6] NodeSource, "NodeSource Node.js Binary Distributions", GitHub. [En línea]. Disponible: https://github.com/nodesource/distributions

[7] systemd, "systemd.service — Service unit configuration". [En línea]. Disponible: https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html

[8] libvirt, "Domain XML format". [En línea]. Disponible: https://libvirt.org/formatdomain.html

[9] libvirt, "virsh — management user interface". [En línea]. Disponible: https://www.libvirt.org/manpages/virsh.html

[10] lxml, "The lxml.etree Tutorial". [En línea]. Disponible: https://lxml.de/tutorial.html

[11] QEMU, "QEMU disk image utility (qemu-img)". [En línea]. Disponible: https://www.qemu.org/docs/master/tools/qemu-img.html

[12] libguestfs, "virt-customize — Customize a virtual machine". [En línea]. Disponible: https://libguestfs.org/virt-customize.1.html

[13] FRRouting, "Static Route Commands (staticd)". [En línea]. Disponible: https://docs.frrouting.org/en/latest/static.html

[14] FRRouting, "VTY shell (vtysh)". [En línea]. Disponible: https://docs.frrouting.org/en/latest/vtysh.html

[15] Python Software Foundation, "logging — Logging facility for Python". [En línea]. Disponible: https://docs.python.org/3/library/logging.html

[16] AMD, "AMD EPYC 9005 Series Processors". [En línea]. Disponible: https://www.amd.com/en/products/processors/server/epyc/9005-series.html

[17] Intel, "Intel Xeon 6 Processors". [En línea]. Disponible: https://www.intel.com/content/www/us/en/products/details/processors/xeon.html

[18] The Linux Kernel documentation, "Kernel Samepage Merging". [En línea]. Disponible: https://docs.kernel.org/admin-guide/mm/ksm.html
