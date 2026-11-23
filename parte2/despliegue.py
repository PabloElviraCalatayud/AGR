#!/usr/bin/env python3
"""
despliegue.py - Despliegue automático de la red del laboratorio 3103 con QEMU-KVM.

AGR - Práctica 2, parte 2. Automatiza los pasos 0-12 de la guía
(doc/entregables/guia_paso_a_paso.pdf) con los ficheros de esta carpeta:

  plantilla.xml        XML de Moodle: de él se generan, con lxml, los de cada VM
  molde/               software común (FRR, Node.js, servidor web)
  vm/<vm>/             configuración de dentro de cada VM (hostname, interfaces,
                       99-router.conf, frr.conf)

Discos en /var/lib/libvirt/images/lab3103:
  base.qcow2   imagen de Moodle (se copia ahí a mano; nunca se modifica)
  molde.qcow2  base + software común (orden "molde")
  <vm>.qcow2   disco diferencial de cada VM sobre el molde

Órdenes (como root):
  sudo ./despliegue.py instalar         dependencias del anfitrión (una vez)
  sudo ./despliegue.py molde            construye molde.qcow2 si no existe
  sudo ./despliegue.py crear            anfitrión + discos + XML + define/start
  sudo ./despliegue.py probar           plan de pruebas de conectividad global
  sudo ./despliegue.py estado
  sudo ./despliegue.py consola ra rb    xterm con 'virsh console' (en segundo plano)
  sudo ./despliegue.py parar | arrancar
  sudo ./despliegue.py destruir         borra VMs, discos de VM, bridges y rutas
       ./despliegue.py xml              sólo genera los XML en xml/ (sin root)
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DIR = Path("/var/lib/libvirt/images/lab3103")
BASE = DIR / "base.qcow2"
MOLDE = DIR / "molde.qcow2"
CLAVE = DIR / "clave_lab"            # clave SSH del anfitrión para las pruebas

DEPENDENCIAS = ["qemu-system-x86", "qemu-utils", "libvirt-daemon-system",
                "libvirt-clients", "libguestfs-tools", "isc-dhcp-client",
                "python3-lxml", "bridge-utils", "xterm", "traceroute",
                "openssh-client", "curl"]

# --- Plan de numeración (doc/development/enunciado/plan_numeracion_3103.pdf) --
# Redes: bridge -> (subred, descripción)
REDES = {
    "br-srv":  ("10.100.0.0/24", "Red de servidores"),
    "br-prof": ("10.200.0.0/30", "PC Profesor (anfitrión)"),
    "br-ab":   ("10.1.0.0/30",   "Enlace RA-RB"),
    "br-bc":   ("10.2.0.0/30",   "Enlace RB-RC"),
    "br-bd":   ("10.3.0.0/30",   "Enlace RB-RD"),
    "br-red1": ("10.0.1.0/24",   "RED 1"),
    "br-red2": ("10.0.2.0/24",   "RED 2"),
    "br-red3": ("10.0.3.0/24",   "RED 3"),
    "br-red4": ("10.0.4.0/24",   "RED 4"),
}
# VMs: nombre -> (rol, [bridge de eth0, eth1, eth2...], [IP de cada tarjeta])
VMS = {
    "srv": ("server", ["br-srv"], ["10.100.0.11"]),
    "ra":  ("router", ["br-srv", "br-ab", "br-prof"], ["10.100.0.1", "10.1.0.1", "10.200.0.1"]),
    "rb":  ("router", ["br-ab", "br-bc", "br-bd"],    ["10.1.0.2", "10.2.0.1", "10.3.0.1"]),
    "rc":  ("router", ["br-bc", "br-red1", "br-red2"], ["10.2.0.2", "10.0.1.1", "10.0.2.1"]),
    "rd":  ("router", ["br-bd", "br-red3", "br-red4"], ["10.3.0.2", "10.0.3.1", "10.0.4.1"]),
    "pc1": ("pc", ["br-red1"], ["10.0.1.10"]),
    "pc2": ("pc", ["br-red2"], ["10.0.2.10"]),
    "pc3": ("pc", ["br-red3"], ["10.0.3.10"]),
    "pc4": ("pc", ["br-red4"], ["10.0.4.10"]),
}
ANFITRION_IP = "10.200.0.2/30"       # PC Profesor, en br-prof
ANFITRION_GW = "10.200.0.1"          # RA ge0/0/5
WEB = "http://10.100.0.11:3000/"
TODAS_LAS_IPS = [ip for _, _, ips in VMS.values() for ip in ips] + ["10.200.0.2"]

# Reaplicar la configuración de FRR al arrancar: si watchfrr reinicia staticd
# por separado (máquina cargada) éste no relee frr.conf y se pierden las rutas.
FRR_DROPIN = """[Service]
ExecStartPost=/bin/sh -c 'for i in $(seq 1 30); do vtysh -c "show version" >/dev/null 2>&1 && break; sleep 2; done; sleep 3; vtysh -b >/dev/null 2>&1 || true'
"""

log = logging.getLogger("despliegue")


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def info(msg):
    """Mensajes que el programa siempre muestra (el enunciado: print)."""
    print(f"\033[1;36m>>>\033[0m {msg}", flush=True)


def sh(cmd, check=True, capture=False, timeout=None):
    """Ejecuta una orden; la registra en las trazas de depuración (-v)."""
    log.debug("$ %s", " ".join(map(str, cmd)))
    r = subprocess.run([str(c) for c in cmd], text=True, capture_output=capture,
                       timeout=timeout)
    if check and r.returncode != 0:
        detalle = (r.stderr or "").strip() if capture else ""
        raise RuntimeError(f"falló: {' '.join(map(str, cmd))}\n{detalle}")
    return r


def virsh(*args, check=True):
    return sh(["virsh", "-c", "qemu:///system", *args], check=check, capture=True)


def root():
    if os.geteuid() != 0:
        sys.exit("Ejecute como root: sudo ./despliegue.py ...")


def seleccion(args):
    vms = getattr(args, "vms", None) or list(VMS)
    for vm in vms:
        if vm not in VMS:
            sys.exit(f"VM desconocida: {vm}. Disponibles: {' '.join(VMS)}")
    return vms


# --------------------------------------------------------------------------
# Anfitrión (lo mismo que red.sh)
# --------------------------------------------------------------------------
def preparar_anfitrion():
    info("Preparando el anfitrión: KVM, bridges, IP de PC Profesor y rutas")
    # KVM y VirtualBox no pueden usar la virtualización del procesador a la vez
    if Path("/sys/module/vboxdrv").exists():
        if sh(["modprobe", "-r", "vboxnetadp", "vboxnetflt", "vboxdrv"],
              check=False, capture=True).returncode != 0:
            log.warning("VirtualBox está en uso (¿VM de la parte 1 encendida? vagrant halt)")
    if not Path("/dev/kvm").exists():
        cpu = Path("/proc/cpuinfo").read_text()
        sh(["modprobe", "kvm_amd" if " svm" in cpu else "kvm_intel"], check=False, capture=True)
    if not Path("/dev/kvm").exists():
        log.warning("/dev/kvm no existe: emulación software (lenta). ¿Virtualización en la BIOS?")
    sh(["systemctl", "start", "libvirtd"], check=False, capture=True)

    for br, (red, desc) in REDES.items():
        if sh(["ip", "link", "show", br], check=False, capture=True).returncode != 0:
            sh(["ip", "link", "add", br, "type", "bridge"])
        sh(["ip", "link", "set", br, "up"])
        log.info("bridge %-8s %-14s %s", br, red, desc)
    # Que el cortafuegos (Docker) no filtre el tráfico entre VMs
    p = Path("/proc/sys/net/bridge/bridge-nf-call-iptables")
    if p.exists():
        p.write_text("0\n")
    # PC Profesor: IP en br-prof y rutas a las redes del laboratorio vía RA
    sh(["ip", "addr", "replace", ANFITRION_IP, "dev", "br-prof"])
    for br, (red, _) in REDES.items():
        if br != "br-prof":
            sh(["ip", "route", "replace", red, "via", ANFITRION_GW])


def limpiar_anfitrion():
    info("Eliminando bridges y rutas del anfitrión")
    for br, (red, _) in REDES.items():
        sh(["ip", "route", "del", red], check=False, capture=True)
        sh(["ip", "link", "del", br], check=False, capture=True)


# --------------------------------------------------------------------------
# XML (lxml, a partir de la plantilla de Moodle)
# --------------------------------------------------------------------------
def generar_xml(vm, disco, ram_mb=None, emular=False):
    """Hace con lxml los mismos cambios que el sed de la guía."""
    try:
        from lxml import etree
    except ImportError:
        sys.exit("Falta lxml: sudo ./despliegue.py instalar")
    arbol = etree.parse(str(AQUI / "plantilla.xml"),
                        etree.XMLParser(remove_blank_text=True))
    raiz = arbol.getroot()
    raiz.find("name").text = vm                               # 1. nombre
    raiz.find("devices/disk/source").set("file", str(disco))  # 2. disco
    if ram_mb:
        for e in ("memory", "currentMemory"):
            raiz.find(e).text = str(ram_mb * 1024)            # KiB
    if emular:                       # sin KVM: emulación software (lenta)
        raiz.set("type", "qemu")

    # 3. una <interface> por bridge, en orden: eth0, eth1, eth2
    devices = raiz.find("devices")
    original = devices.find("interface")
    pos = list(devices).index(original)
    devices.remove(original)
    for i, br in enumerate(VMS[vm][1]):
        itf = etree.Element("interface", type="bridge")
        etree.SubElement(itf, "source", bridge=br)
        etree.SubElement(itf, "model", type="virtio")
        devices.insert(pos + i, itf)
    return etree.tostring(arbol, pretty_print=True, encoding="unicode")


# --------------------------------------------------------------------------
# Discos
# --------------------------------------------------------------------------
def clave_ssh():
    if not CLAVE.exists():
        sh(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "lab3103",
            "-f", CLAVE])
    return CLAVE.with_suffix(".pub")


def crear_disco(vm):
    """Disco diferencial sobre el molde + configuración escrita antes de arrancar."""
    disco = DIR / f"{vm}.qcow2"
    disco.unlink(missing_ok=True)
    sh(["qemu-img", "create", "-q", "-f", "qcow2", "-F", "qcow2", "-b", MOLDE, disco])

    cfg = AQUI / "vm" / vm
    cmd = ["virt-customize", "-q", "-a", disco,
           "--hostname", vm,
           "--upload", f"{cfg / 'interfaces'}:/etc/network/interfaces",
           "--ssh-inject", f"root:file:{clave_ssh()}",
           # claves de host propias de cada VM (las imágenes cloud no las traen
           # y sin ellas sshd no arranca)
           "--run-command", "rm -f /etc/ssh/ssh_host_* && ssh-keygen -A"]
    rol = VMS[vm][0]
    if rol == "router":
        dropin = Path(tempfile.mkdtemp()) / "lab3103.conf"
        dropin.write_text(FRR_DROPIN)
        cmd += ["--upload", f"{cfg / '99-router.conf'}:/etc/sysctl.d/99-router.conf",
                "--upload", f"{cfg / 'frr.conf'}:/etc/frr/frr.conf",
                "--run-command", "chown frr:frr /etc/frr/frr.conf && chmod 640 /etc/frr/frr.conf",
                "--mkdir", "/etc/systemd/system/frr.service.d",
                "--upload", f"{dropin}:/etc/systemd/system/frr.service.d/lab3103.conf",
                "--run-command",
                "sed -i 's/^#*watchfrr_options=.*/watchfrr_options=\"-t 60 -T 90\"/' /etc/frr/daemons || true",
                "--run-command", "systemctl enable frr"]
    elif rol == "server":
        cmd += ["--run-command", "systemctl enable ssr-server"]
    sh(cmd)
    return disco


# --------------------------------------------------------------------------
# Órdenes
# --------------------------------------------------------------------------
def cmd_instalar(args):
    root()
    info("Instalando: " + " ".join(DEPENDENCIAS))
    sh(["apt-get", "update"])
    sh(["apt-get", "install", "-y", *DEPENDENCIAS])
    sh(["systemctl", "enable", "--now", "libvirtd"], check=False)


def cmd_molde(args):
    """Construye molde.qcow2 sobre base.qcow2 con el software común."""
    root()
    if MOLDE.exists() and not args.rehacer:
        info(f"El molde ya existe: {MOLDE} (use --rehacer para construirlo de nuevo)")
        return
    if not BASE.exists():
        sys.exit(f"Falta la imagen de Moodle: cópiela como {BASE}")
    if args.rehacer:
        info("Al rehacer el molde hay que recrear las VMs (sus discos dependen de él)")
        for vm in VMS:
            virsh("destroy", vm, check=False); virsh("undefine", vm, check=False)
            (DIR / f"{vm}.qcow2").unlink(missing_ok=True)
        MOLDE.unlink(missing_ok=True)
    os.environ.setdefault("LIBGUESTFS_BACKEND", "direct")
    info("Construyendo el molde: FRR, Node.js y servidor web (varios minutos)...")
    tmp = DIR / "molde.tmp"
    tmp.unlink(missing_ok=True)
    sh(["qemu-img", "create", "-q", "-f", "qcow2", "-F", "qcow2", "-b", BASE, tmp])
    # Con proxy (p. ej. de la universidad), también para npm si inspecciona TLS
    env = (f"http_proxy={args.proxy} https_proxy={args.proxy} "
           "NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt " if args.proxy else "")
    sh(["virt-customize", "-a", tmp, "--network",
        "--upload", f"{AQUI / 'molde' / 'ssr-server.service'}:/etc/systemd/system/ssr-server.service",
        "--upload", f"{AQUI / 'molde' / 'preparar_molde.sh'}:/root/preparar_molde.sh",
        "--run-command", f"{env}bash /root/preparar_molde.sh",
        "--delete", "/root/preparar_molde.sh"])
    tmp.rename(MOLDE)
    MOLDE.chmod(0o444)
    info(f"Molde listo: {MOLDE}")


def cmd_xml(args):
    salida = AQUI / "xml"
    salida.mkdir(exist_ok=True)
    for vm in seleccion(args):
        (salida / f"{vm}.xml").write_text(generar_xml(vm, DIR / f"{vm}.qcow2", args.ram))
    print(f"XML generados en {salida}")


def cmd_crear(args):
    root()
    os.environ.setdefault("LIBGUESTFS_BACKEND", "direct")
    if not MOLDE.exists():
        cmd_molde(argparse.Namespace(rehacer=False, proxy=args.proxy))
    preparar_anfitrion()
    xmls = DIR / "xml"
    xmls.mkdir(exist_ok=True)
    for vm in seleccion(args):
        info(f"VM {vm} ({VMS[vm][0]}): " +
             ", ".join(f"eth{i} {br} {ip}" for i, (br, ip) in enumerate(zip(VMS[vm][1], VMS[vm][2]))))
        virsh("destroy", vm, check=False)
        virsh("undefine", vm, check=False)
        disco = crear_disco(vm)
        xml = xmls / f"{vm}.xml"
        xml.write_text(generar_xml(vm, disco, args.ram,
                                   emular=not Path("/dev/kvm").exists()))
        virsh("define", xml)
        virsh("start", vm)
    esperar(seleccion(args), args.espera)
    cmd_estado(args)
    print("\nSiguiente paso: sudo ./despliegue.py probar")


def cmd_arrancar(args):
    root()
    preparar_anfitrion()
    for vm in seleccion(args):
        r = virsh("start", vm, check=False)
        print(f"{vm}: {'arrancada' if r.returncode == 0 else r.stderr.strip()}")


def cmd_parar(args):
    root()
    for vm in seleccion(args):
        virsh("shutdown", vm, check=False)
    fin = time.time() + 120
    while virsh("list", "--name").stdout.strip() and time.time() < fin:
        time.sleep(2)
    print("Apagadas:", " ".join(seleccion(args)))


def cmd_destruir(args):
    root()
    for vm in seleccion(args):
        virsh("destroy", vm, check=False)
        virsh("undefine", vm, check=False)
        (DIR / f"{vm}.qcow2").unlink(missing_ok=True)
        (DIR / "xml" / f"{vm}.xml").unlink(missing_ok=True)
        print(f"{vm}: eliminada")
    if not args.vms:
        limpiar_anfitrion()
    print(f"Se conservan {BASE.name} y {MOLDE.name} en {DIR}")


def cmd_estado(args):
    print(f"\n{'VM':<5} {'ESTADO':<12} {'ROL':<7} TARJETAS")
    for vm, (rol, brs, ips) in VMS.items():
        r = virsh("domstate", vm, check=False)
        estado = r.stdout.strip() if r.returncode == 0 else "no definida"
        tarjetas = "  ".join(f"eth{i}:{br}:{ip}" for i, (br, ip) in enumerate(zip(brs, ips)))
        print(f"{vm:<5} {estado:<12} {rol:<7} {tarjetas}")


def cmd_consola(args):
    for vm in seleccion(args):
        if shutil.which("xterm"):
            subprocess.Popen(["xterm", "-T", vm, "-e", f"virsh -c qemu:///system console {vm}"],
                             start_new_session=True, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            print(f"{vm}: consola abierta (root / agr; salir con Ctrl+])")
        else:
            print(f"Sin xterm: sudo virsh console {vm}")


# --- Pruebas -----------------------------------------------------------------
def ping(ip, n=1):
    return sh(["ping", "-c", str(n), "-W", "2", ip], check=False, capture=True).returncode == 0


def ssh(ip, orden, timeout=60):
    """Orden remota; si no contesta a tiempo devuelve código 124 (como timeout)."""
    cmd = ["ssh", "-i", CLAVE, "-o", "StrictHostKeyChecking=no",
           "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=5",
           "-o", "LogLevel=ERROR", f"root@{ip}", orden]
    try:
        return sh(cmd, check=False, capture=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        log.debug("ssh %s: sin respuesta en %ss", ip, timeout)
        return subprocess.CompletedProcess(cmd, 124, "", "timeout")


def esperar(vms, timeout):
    info("Esperando a que arranquen las VMs...")
    pendientes = set(vms)
    primer_ping = {}
    fin = time.time() + timeout
    while pendientes and time.time() < fin:
        for vm in sorted(pendientes):
            ip = VMS[vm][2][0]
            ok = ping(ip)
            if ok:
                primer_ping.setdefault(vm, time.time())
            if ok and VMS[vm][0] == "router":     # rutas instaladas por FRR
                r = ssh(ip, "ip route | grep -q '^default'", 15)
                # sin SSH no se puede mirar dentro: basta con 60 s respondiendo
                ok = r.returncode == 0 or (r.returncode == 255
                                           and time.time() - primer_ping[vm] > 60)
            if ok and VMS[vm][0] == "server":     # servidor web escuchando
                ok = sh(["curl", "-s", "-o", "/dev/null", "--max-time", "5", WEB],
                        check=False, capture=True).returncode == 0
            if ok:
                log.info("%s lista", vm)
                pendientes.discard(vm)
        if pendientes:
            time.sleep(3)
    if pendientes:
        log.warning("No responden tras %ss: %s", timeout, " ".join(sorted(pendientes)))


PRUEBA_VM = ("ok=0; fail=''; for ip in " + " ".join(TODAS_LAS_IPS) + "; do "
             "if ping -c1 -W1 $ip >/dev/null 2>&1; then ok=$((ok+1)); "
             "else fail=\"$fail $ip\"; fi; done; "
             "web=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 " + WEB + "); "
             "echo \"$ok $web$fail\"")


def cmd_probar(args):
    root()
    resultados, informe = [], []

    def anotar(origen, prueba, ok, detalle=""):
        resultados.append(ok)
        marca = "\033[32mOK   \033[0m" if ok else "\033[31mFALLO\033[0m"
        print(f"  {marca} {origen:<9} {prueba}")
        informe.append(f"[{'OK' if ok else 'FALLO'}] {origen:<9} {prueba}")
        if detalle:
            informe.extend("      " + l for l in detalle.strip().splitlines())

    esperar(list(VMS), args.espera)

    print("\n1) Anfitrión (PC Profesor) -> todas las IPs del laboratorio y servidor web")
    for vm, (_, _, ips) in VMS.items():
        for ip in ips:
            anotar("anfitrion", f"ping {ip:<12} ({vm})", ping(ip, 2))
    r = sh(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "15", WEB],
           check=False, capture=True)
    anotar("anfitrion", f"HTTP GET {WEB} -> {r.stdout}", r.stdout == "200")
    r = sh(["curl", "-s", "--max-time", "15",
            WEB + "record?id_nodo=prueba&temperatura=21&humedad=40&co2=400&volatiles=10"],
           check=False, capture=True)
    anotar("anfitrion", "HTTP GET /record (escritura de datos)", "Saving" in r.stdout)

    print("\n2) Caminos desde el anfitrión (traceroute a cada PC)")
    for vm in ("pc1", "pc2", "pc3", "pc4"):
        ip = VMS[vm][2][0]
        r = sh(["traceroute", "-n", "-w", "2", "-q", "1", ip], check=False, capture=True)
        lineas = r.stdout.strip().splitlines()
        anotar("anfitrion", f"traceroute {ip}", bool(lineas) and ip in lineas[-1], r.stdout)

    print("\n3) Desde cada VM: ping a las 18 IPs y acceso web (por SSH)")
    for vm, (rol, _, ips) in VMS.items():
        r = ssh(ips[0], PRUEBA_VM, 120)
        if r.returncode != 0 or not r.stdout.strip():
            anotar(vm, "conectividad global (sin acceso SSH)", False, r.stderr)
            continue
        ok, web, *fallan = r.stdout.split()
        anotar(vm, f"{ok}/{len(TODAS_LAS_IPS)} IPs, web={web}"
               + (f", fallan: {' '.join(fallan)}" if fallan else ""),
               ok == str(len(TODAS_LAS_IPS)) and web == "200")

    print("\n4) Tablas de rutas de los routers (FRR)")
    for vm, (rol, _, ips) in VMS.items():
        if rol == "router":
            r = ssh(ips[0], "vtysh -c 'show ip route' | grep -E '^[CS]'")
            anotar(vm, "show ip route", r.returncode == 0 and "S>*" in r.stdout, r.stdout)

    total, ok = len(resultados), sum(resultados)
    print(f"\nResultado: {ok}/{total} pruebas correctas")
    if args.informe:
        Path(args.informe).write_text(
            f"Plan de pruebas - {datetime.now():%Y-%m-%d %H:%M:%S}\n"
            f"Resultado: {ok}/{total} pruebas correctas\n\n" + "\n".join(informe) + "\n")
        print(f"Informe guardado en {args.informe}")
    return 0 if ok == total else 1


# --------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="Laboratorio 3103 con QEMU-KVM (AGR)",
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=__doc__)
    p.add_argument("-v", "--verbose", action="store_true", help="trazas de depuración")
    sub = p.add_subparsers(dest="orden", required=True)

    def orden(nombre, func, ayuda, vms=False):
        s = sub.add_parser(nombre, help=ayuda)
        s.set_defaults(func=func)
        if vms:
            s.add_argument("vms", nargs="*", help="sólo estas VMs (por defecto todas)")
        return s

    orden("instalar", cmd_instalar, "instala las dependencias del anfitrión")
    s = orden("molde", cmd_molde, "construye molde.qcow2 (software común)")
    s.add_argument("--rehacer", action="store_true", help="vuelve a construirlo (recrea las VMs)")
    s.add_argument("--proxy", help="proxy HTTP(S) para descargar paquetes")
    s = orden("crear", cmd_crear, "despliega las VMs (discos, XML, define, start)", vms=True)
    s.add_argument("--ram", type=int, help="RAM por VM en MB (por defecto, la de la plantilla)")
    s.add_argument("--espera", type=int, default=300, help="segundos de espera al arranque")
    s.add_argument("--proxy", help="proxy para construir el molde si no existe")
    orden("arrancar", cmd_arrancar, "prepara el anfitrión y arranca las VMs", vms=True)
    orden("parar", cmd_parar, "apaga las VMs ordenadamente", vms=True)
    orden("destruir", cmd_destruir, "elimina VMs, sus discos, bridges y rutas", vms=True)
    orden("estado", cmd_estado, "estado de las VMs")
    orden("consola", cmd_consola, "abre un xterm con la consola de cada VM", vms=True)
    s = orden("probar", cmd_probar, "plan de pruebas de conectividad global")
    s.add_argument("--informe", help="guarda el resultado en este fichero")
    s.add_argument("--espera", type=int, default=180)
    s = orden("xml", cmd_xml, "sólo genera los XML en xml/", vms=True)
    s.add_argument("--ram", type=int)

    args = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s: %(message)s")
    try:
        sys.exit(args.func(args) or 0)
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        log.error("%s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
